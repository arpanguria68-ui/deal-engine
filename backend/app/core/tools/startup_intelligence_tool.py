"""
Startup Intelligence Tool — Crunchbase & BrightData-Style Company Research

Scrapes publicly available startup data WITHOUT requiring API keys by leveraging:
1. DuckDuckGo search targeting Crunchbase/BrightData pages
2. Direct scraping of public Crunchbase company profiles
3. Google-indexed financial data aggregation
4. TechCrunch / PitchBook / LinkedIn public data extraction

Data extracted: funding rounds, investors, employees, revenue range, industry, etc.
"""

import re
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import quote_plus
import structlog

from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger()

# ─── Search queries targeting specific data sources ───
SEARCH_TEMPLATES = {
    "crunchbase_profile": "site:crunchbase.com/organization {company}",
    "crunchbase_funding": "site:crunchbase.com {company} funding rounds investors",
    "pitchbook_profile": "site:pitchbook.com {company} company profile",
    "linkedin_company": "site:linkedin.com/company {company}",
    "techcrunch_funding": "site:techcrunch.com {company} funding raised",
    "general_funding": "{company} funding round series valuation investors",
    "general_revenue": "{company} revenue ARR annual recurring revenue employees",
    "general_competitors": "{company} competitors alternatives market share",
    "sec_filings": "site:sec.gov {company} S-1 10-K filing",
    "glassdoor": "site:glassdoor.com {company} company reviews employees",
}


class StartupIntelligenceTool(BaseTool):
    """
    Scrapes publicly available startup data from Crunchbase, PitchBook, TechCrunch
    and other public sources — no API keys required.

    Uses DuckDuckGo search to find relevant pages, then extracts structured data.
    """

    def __init__(self):
        super().__init__(
            name="startup_intelligence",
            description="Research startups by scraping Crunchbase, PitchBook, TechCrunch "
            "and other public sources. No API key needed. Extracts funding, "
            "investors, revenue estimates, employee count, and competitive landscape.",
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Company name to research (e.g. 'Zapier', 'Stripe')",
                },
                "depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "deep"],
                    "description": "Research depth: quick (2 queries), standard (5), deep (all 10)",
                    "default": "standard",
                },
            },
            "required": ["company"],
        }

    async def execute_async(
        self,
        company: str,
        depth: str = "standard",
    ) -> ToolResult:
        """Run multi-source startup intelligence gathering."""
        try:
            logger.info("startup_intel_start", company=company, depth=depth)

            # Select queries based on depth
            if depth == "quick":
                query_keys = ["crunchbase_profile", "general_funding"]
            elif depth == "deep":
                query_keys = list(SEARCH_TEMPLATES.keys())
            else:
                query_keys = [
                    "crunchbase_profile",
                    "crunchbase_funding",
                    "general_funding",
                    "general_revenue",
                    "general_competitors",
                ]

            # Execute searches in parallel
            search_results = await self._multi_search(company, query_keys)

            # Extract and structure data
            profile = self._extract_profile(company, search_results)

            return ToolResult(
                success=True,
                data={
                    "company": company,
                    "profile": profile,
                    "sources": list(search_results.keys()),
                    "scrape_timestamp": datetime.utcnow().isoformat(),
                },
            )

        except Exception as e:
            logger.error("startup_intel_error", company=company, error=str(e))
            return ToolResult(success=False, data=None, error=str(e))

    async def execute(self, company: str = "", depth: str = "standard") -> ToolResult:
        """Execute startup intelligence gathering."""
        return await self.execute_async(company, depth)

    async def _multi_search(
        self, company: str, query_keys: List[str]
    ) -> Dict[str, List[Dict]]:
        """Run multiple DuckDuckGo searches in parallel."""
        results = {}

        async def _search_one(key: str):
            query = SEARCH_TEMPLATES[key].format(company=company)
            try:
                from duckduckgo_search import DDGS

                with DDGS() as ddgs:
                    hits = list(ddgs.text(query, max_results=5))
                    results[key] = [
                        {
                            "title": h.get("title", ""),
                            "href": h.get("href", ""),
                            "body": h.get("body", ""),
                        }
                        for h in hits
                    ]
            except Exception as e:
                logger.warning("search_failed", key=key, error=str(e))
                results[key] = []

        tasks = [_search_one(k) for k in query_keys]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    def _extract_profile(
        self, company: str, search_results: Dict[str, List[Dict]]
    ) -> Dict:
        """Extract structured company profile from search snippets."""
        all_text = ""
        for key, results in search_results.items():
            for r in results:
                all_text += f" {r.get('title', '')} {r.get('body', '')}"

        profile = {
            "company_name": company,
            "funding": self._extract_funding(all_text),
            "investors": self._extract_investors(all_text),
            "revenue_estimate": self._extract_revenue(all_text),
            "employee_count": self._extract_employees(all_text),
            "industry": self._extract_industry(all_text),
            "founded": self._extract_year(all_text, "founded"),
            "headquarters": self._extract_headquarters(all_text),
            "valuation": self._extract_valuation(all_text),
            "competitors": self._extract_competitors(all_text, company),
            "key_links": self._extract_links(search_results),
        }

        # Confidence score based on how much data was found
        filled = sum(1 for v in profile.values() if v and v != "Unknown")
        profile["data_confidence"] = round(filled / len(profile), 2)

        return profile

    # ─── Extraction Helpers ───────────────────────────────

    @staticmethod
    def _extract_funding(text: str) -> Dict:
        """Extract funding information from text snippets."""
        funding = {"total_raised": "Unknown", "last_round": "Unknown", "rounds": []}

        # Total raised patterns
        patterns = [
            r"raised?\s+(?:a total of\s+)?\$?([\d,.]+)\s*(million|billion|[MmBb])",
            r"\$?([\d,.]+)\s*(million|billion|[MmBb])\s+(?:in\s+)?(?:total\s+)?funding",
            r"total funding[:\s]+\$?([\d,.]+)\s*(million|billion|[MmBb])?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(",", ""))
                unit = match.group(2).lower() if match.group(2) else "m"
                if unit.startswith("b"):
                    amount *= 1000
                funding["total_raised"] = f"${amount:,.0f}M"
                break

        # Series / round patterns
        series_pattern = r"(Series\s+[A-Z]|Seed|Pre-Seed|Angel|Growth|IPO)\s+(?:round\s+)?(?:of\s+)?\$?([\d,.]+)\s*(million|billion|[MmBb])?"
        for match in re.finditer(series_pattern, text, re.IGNORECASE):
            round_name = match.group(1)
            amount = float(match.group(2).replace(",", ""))
            unit = match.group(3).lower() if match.group(3) else "m"
            if unit.startswith("b"):
                amount *= 1000
            funding["rounds"].append(
                {"round": round_name, "amount": f"${amount:,.0f}M"}
            )
            funding["last_round"] = round_name

        return funding

    @staticmethod
    def _extract_investors(text: str) -> List[str]:
        """Extract investor names from text."""
        investors = set()
        # Known VC/PE patterns
        vc_names = [
            "Sequoia",
            "Andreessen Horowitz",
            "a16z",
            "Benchmark",
            "Accel",
            "Greylock",
            "Lightspeed",
            "Index Ventures",
            "General Catalyst",
            "Tiger Global",
            "SoftBank",
            "Insight Partners",
            "Thoma Bravo",
            "Vista Equity",
            "KKR",
            "Blackstone",
            "Carlyle",
            "Apollo",
            "GIC",
            "Temasek",
            "Coatue",
            "Ribbit Capital",
            "Founders Fund",
            "Y Combinator",
            "500 Startups",
            "NEA",
            "Bessemer",
            "IVP",
            "GGV Capital",
            "DST Global",
            "Silver Lake",
            "Warburg Pincus",
            "Goldman Sachs",
            "Morgan Stanley",
            "JP Morgan",
            "Steadfast",
        ]
        text_lower = text.lower()
        for vc in vc_names:
            if vc.lower() in text_lower:
                investors.add(vc)

        # Also look for "led by X" or "backed by X" patterns
        lead_pattern = (
            r"(?:led|backed|funded|invested)\s+by\s+([A-Z][A-Za-z\s&]+?)(?:[,\.]|and)"
        )
        for match in re.finditer(lead_pattern, text):
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 40:
                investors.add(name)

        return list(investors)[:15]

    @staticmethod
    def _extract_revenue(text: str) -> str:
        """Extract revenue/ARR estimates."""
        patterns = [
            r"(?:ARR|annual recurring revenue|revenue)\s+(?:of\s+)?(?:approximately\s+)?(?:around\s+)?\$?([\d,.]+)\s*(million|billion|[MmBb])",
            r"\$?([\d,.]+)\s*(million|billion|[MmBb])\s+(?:in\s+)?(?:ARR|annual recurring revenue|revenue)",
            r"revenue[:\s]+\$?([\d,.]+)\s*(million|billion|[MmBb])?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(",", ""))
                unit = match.group(2).lower() if match.group(2) else "m"
                if unit.startswith("b"):
                    amount *= 1000
                return f"~${amount:,.0f}M"
        return "Unknown"

    @staticmethod
    def _extract_employees(text: str) -> str:
        """Extract employee count."""
        patterns = [
            r"([\d,]+)\s*(?:\+\s*)?employees",
            r"(?:team of|headcount|staff)\s*(?:of\s+)?([\d,]+)",
            r"([\d,]+)\s*(?:people|team members|workers)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count = match.group(1).replace(",", "")
                return f"~{int(count):,}"
        return "Unknown"

    @staticmethod
    def _extract_industry(text: str) -> str:
        """Extract industry classification."""
        industries = {
            "SaaS": ["saas", "software as a service", "cloud software"],
            "Fintech": ["fintech", "financial technology", "payments"],
            "AI/ML": ["artificial intelligence", "machine learning", "ai platform"],
            "E-commerce": ["e-commerce", "ecommerce", "marketplace"],
            "Healthtech": ["healthtech", "health tech", "healthcare technology"],
            "Edtech": ["edtech", "education technology"],
            "Cybersecurity": ["cybersecurity", "security platform"],
            "DevTools": ["developer tools", "devops", "developer platform"],
            "Enterprise": ["enterprise software", "b2b software"],
            "Automation": ["automation", "workflow automation", "no-code"],
            "Infrastructure": ["cloud infrastructure", "data infrastructure"],
        }
        text_lower = text.lower()
        matches = []
        for industry, keywords in industries.items():
            for kw in keywords:
                if kw in text_lower:
                    matches.append(industry)
                    break
        return ", ".join(matches[:3]) if matches else "Technology"

    @staticmethod
    def _extract_year(text: str, context: str) -> str:
        """Extract a year near a context keyword."""
        pattern = rf"{context}\s+(?:in\s+)?((?:19|20)\d{{2}})"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else "Unknown"

    @staticmethod
    def _extract_headquarters(text: str) -> str:
        """Extract HQ location."""
        cities = [
            "San Francisco",
            "New York",
            "Austin",
            "Seattle",
            "Boston",
            "Chicago",
            "Los Angeles",
            "Denver",
            "Miami",
            "London",
            "Berlin",
            "Paris",
            "Singapore",
            "Toronto",
            "Sydney",
            "Tel Aviv",
            "Bangalore",
            "Mumbai",
            "São Paulo",
            "Palo Alto",
            "Mountain View",
            "San Jose",
            "Menlo Park",
        ]
        for city in cities:
            if city.lower() in text.lower():
                return city
        return "Unknown"

    @staticmethod
    def _extract_valuation(text: str) -> str:
        """Extract company valuation."""
        patterns = [
            r"(?:valued at|valuation of?|worth)\s+\$?([\d,.]+)\s*(million|billion|[MmBb])",
            r"\$?([\d,.]+)\s*(million|billion|[MmBb])\s+valuation",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(",", ""))
                unit = match.group(2).lower()
                if unit.startswith("b"):
                    return f"${amount:.1f}B"
                return f"${amount:,.0f}M"
        return "Unknown"

    @staticmethod
    def _extract_competitors(text: str, company: str) -> List[str]:
        """Extract competitor names."""
        competitors = set()
        patterns = [
            r"(?:competitors?|alternatives?|competes? with|vs\.?|versus)\s*(?:include\s+|:?\s+)([A-Z][A-Za-z\s,&]+?)(?:\.|$)",
            r"([A-Z][A-Za-z]+)\s+(?:and|,)\s+([A-Z][A-Za-z]+)\s+are\s+(?:competitors?|rivals?)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                names = match.group(1).split(",")
                for n in names:
                    name = n.strip().split(" and ")
                    for nm in name:
                        nm = nm.strip()
                        if (
                            nm
                            and nm.lower() != company.lower()
                            and len(nm) > 1
                            and len(nm) < 30
                        ):
                            competitors.add(nm)
        return list(competitors)[:10]

    @staticmethod
    def _extract_links(search_results: Dict[str, List[Dict]]) -> Dict[str, str]:
        """Extract key reference URLs."""
        links = {}
        for key, results in search_results.items():
            for r in results:
                href = r.get("href", "")
                if "crunchbase.com/organization" in href and "crunchbase" not in links:
                    links["crunchbase"] = href
                elif "pitchbook.com" in href and "pitchbook" not in links:
                    links["pitchbook"] = href
                elif "linkedin.com/company" in href and "linkedin" not in links:
                    links["linkedin"] = href
                elif "techcrunch.com" in href and "techcrunch" not in links:
                    links["techcrunch"] = href
                elif "sec.gov" in href and "sec_filing" not in links:
                    links["sec_filing"] = href
        return links
