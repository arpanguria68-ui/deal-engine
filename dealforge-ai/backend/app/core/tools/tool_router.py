"""Tool Router for Agent Tool Calling — With External Data & Report Generation Tools"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
import json
import time
import structlog

logger = structlog.get_logger()


# ═══════════════════════════════════════════════
#  Core Framework
# ═══════════════════════════════════════════════


@dataclass
class ToolResult:
    """Result of a tool execution"""

    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


class BaseTool(ABC):
    """Base class for all tools"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        pass


# ═══════════════════════════════════════════════
#  1. Financial Calculator (existing, improved)
# ═══════════════════════════════════════════════


class FinancialCalculatorTool(BaseTool):
    """Tool for financial calculations — DCF, multiples, ratios"""

    def __init__(self):
        super().__init__(
            name="financial_calculator",
            description="Calculate financial metrics: DCF valuation, revenue multiples, financial ratios, NPV, and IRR",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "calculation_type": {
                    "type": "string",
                    "enum": ["dcf", "multiple", "ratio", "npv", "irr"],
                    "description": "Type of financial calculation",
                },
                "inputs": {
                    "type": "object",
                    "description": "Input parameters for the calculation",
                },
            },
            "required": ["calculation_type", "inputs"],
        }

    async def execute(self, calculation_type: str, inputs: Dict) -> ToolResult:
        try:
            result = {}
            if calculation_type == "dcf":
                cash_flows = inputs.get("cash_flows", [])
                discount_rate = inputs.get("discount_rate", 0.1)
                terminal_growth = inputs.get("terminal_growth", 0.02)
                pv = 0
                for i, cf in enumerate(cash_flows):
                    pv += cf / ((1 + discount_rate) ** (i + 1))
                if cash_flows:
                    terminal_value = (
                        cash_flows[-1]
                        * (1 + terminal_growth)
                        / (discount_rate - terminal_growth)
                    )
                    pv += terminal_value / ((1 + discount_rate) ** len(cash_flows))
                result = {"dcf_value": round(pv, 2)}
            elif calculation_type == "multiple":
                revenue = inputs.get("revenue", 0)
                multiple = inputs.get("multiple", 5)
                result = {"valuation": round(revenue * multiple, 2)}
            elif calculation_type == "ratio":
                numerator = inputs.get("numerator", 0)
                denominator = inputs.get("denominator", 1)
                ratio_name = inputs.get("ratio_name", "ratio")
                result = {
                    ratio_name: round(numerator / denominator, 4) if denominator else 0
                }
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ═══════════════════════════════════════════════
#  2. Document Search (PageIndex RAG)
# ═══════════════════════════════════════════════


class DocumentSearchTool(BaseTool):
    """Search through indexed documents via PageIndex RAG"""

    def __init__(self, pageindex_client):
        super().__init__(
            name="document_search",
            description="Search through indexed deal documents for relevant financial, legal, or market information",
        )
        self.pageindex = pageindex_client

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "index_id": {
                    "type": "string",
                    "description": "Optional specific index to search",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, query: str, index_id: Optional[str] = None, top_k: int = 5
    ) -> ToolResult:
        try:
            chunks = await self.pageindex.query(query, index_id, top_k)
            results = [
                {
                    "content": chunk.content,
                    "page": chunk.page_number,
                    "relevance": chunk.relevance_score,
                }
                for chunk in chunks
            ]
            return ToolResult(success=True, data={"results": results})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ═══════════════════════════════════════════════
#  3. DuckDuckGo Web Search (NEW — real external)
# ═══════════════════════════════════════════════


class DuckDuckGoSearchTool(BaseTool):
    """Search the web using DuckDuckGo — no API key required"""

    def __init__(self):
        super().__init__(
            name="web_search",
            description="Search the web for real-time company news, market data, competitor analysis, and industry trends using DuckDuckGo",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'Zapier automation SaaS market share 2024')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        t0 = time.time()
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
            ]
            elapsed = round((time.time() - t0) * 1000, 1)
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results_count": len(results),
                    "results": results,
                },
                execution_time_ms=elapsed,
            )
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                error="duckduckgo-search package not installed. Run: pip install duckduckgo-search",
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"Web search failed: {str(e)}"
            )


# ═══════════════════════════════════════════════
#  4. Web Scraper (NEW — fetch & extract page text)
# ═══════════════════════════════════════════════


class WebScraperTool(BaseTool):
    """Fetch and extract text content from a web page URL"""

    def __init__(self):
        super().__init__(
            name="web_scraper",
            description="Visit a website URL and extract its text content — useful for reading company pages, SEC filings, press releases, and blog posts",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to visit (e.g., https://zapier.com/about)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 5000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_chars: int = 5000) -> ToolResult:
        t0 = time.time()
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "DealForge-AI/1.0"})
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove noise: scripts, styles, nav, footer
            for tag in soup(
                ["script", "style", "nav", "footer", "header", "aside", "noscript"]
            ):
                tag.decompose()

            title = (
                soup.title.string.strip() if soup.title and soup.title.string else ""
            )
            meta_desc = ""
            meta_tag = soup.find("meta", attrs={"name": "description"})
            if meta_tag and meta_tag.get("content"):
                meta_desc = meta_tag["content"]

            text = soup.get_text(separator="\n", strip=True)
            # Collapse blank lines
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            clean_text = "\n".join(lines)[:max_chars]

            elapsed = round((time.time() - t0) * 1000, 1)
            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "title": title,
                    "meta_description": meta_desc,
                    "text": clean_text,
                    "chars": len(clean_text),
                },
                execution_time_ms=elapsed,
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"Failed to scrape {url}: {str(e)}"
            )


# ═══════════════════════════════════════════════
#  5. SEC EDGAR Filings (NEW — real external)
# ═══════════════════════════════════════════════


class SECFilingsTool(BaseTool):
    """Search SEC EDGAR for public company filings (10-K, 10-Q, 8-K)"""

    def __init__(self):
        super().__init__(
            name="sec_filings",
            description="Search SEC EDGAR for public company regulatory filings — 10-K annual reports, 10-Q quarterly, 8-K events. Only works for US publicly traded companies.",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Company name to search for (e.g., 'Salesforce')",
                },
                "filing_type": {
                    "type": "string",
                    "enum": ["10-K", "10-Q", "8-K", "all"],
                    "description": "Filing type filter",
                    "default": "all",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum filings to return",
                    "default": 5,
                },
            },
            "required": ["company_name"],
        }

    async def execute(
        self, company_name: str, filing_type: str = "all", max_results: int = 5
    ) -> ToolResult:
        t0 = time.time()
        try:
            import httpx

            # SEC EDGAR full-text search API
            params = {
                "q": company_name,
                "dateRange": "custom",
                "startdt": "2023-01-01",
                "enddt": "2025-12-31",
            }
            if filing_type != "all":
                params["forms"] = filing_type

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params=params,
                    headers={
                        "User-Agent": "DealForge-AI research@dealforge.ai",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            hits = data.get("hits", {}).get("hits", [])[:max_results]
            filings = []
            for hit in hits:
                src = hit.get("_source", {})
                filings.append(
                    {
                        "company": (
                            src.get("display_names", [company_name])[0]
                            if src.get("display_names")
                            else company_name
                        ),
                        "form_type": src.get("form_type", "unknown"),
                        "filed_date": src.get("file_date", ""),
                        "description": src.get("display_date_filed", ""),
                        "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id', '')}/{src.get('file_num', '')}",
                    }
                )

            elapsed = round((time.time() - t0) * 1000, 1)

            if not filings:
                return ToolResult(
                    success=True,
                    data={
                        "company": company_name,
                        "note": f"No SEC filings found for '{company_name}'. The company may be private or non-US.",
                        "filings": [],
                    },
                    execution_time_ms=elapsed,
                )

            return ToolResult(
                success=True,
                data={
                    "company": company_name,
                    "filings_found": len(filings),
                    "filings": filings,
                },
                execution_time_ms=elapsed,
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"SEC EDGAR search failed: {str(e)}"
            )


#  6. SEC Filing Section Extractor (Advanced — sec-api.io)
# ═══════════════════════════════════════════════════════════


class SECExtractorTool(BaseTool):
    """Extract specific sections (Risk Factors, MD&A, etc.) from SEC filings using sec-api.io"""

    def __init__(self):
        super().__init__(
            name="sec_section_extractor",
            description="Extract specific sections from a 10-K, 10-Q, or 8-K filing. Requires an SEC_API_KEY. Sections include: '1A' (Risk Factors), '7' (MD&A), '1' (Business), '2' (Properties), '3' (Legal Proceedings).",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to the SEC filing HTML (from sec_filings tool)",
                },
                "section": {
                    "type": "string",
                    "description": "Section code to extract (e.g., '1A', '7', '1')",
                    "default": "1A",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, section: str = "1A") -> ToolResult:
        t0 = time.time()
        from app.config import get_settings

        settings = get_settings()
        api_key = settings.SEC_API_KEY

        if not api_key:
            return ToolResult(
                success=False,
                data=None,
                error="SEC_API_KEY not configured. SECExtractorTool requires a sec-api.io API key.",
            )

        try:
            from sec_api import ExtractorApi

            extractor = ExtractorApi(api_key)
            # SEC API Extractor is a synchronous call → run in thread
            import asyncio

            text = await asyncio.to_thread(extractor.get_section, url, section, "text")

            elapsed = round((time.time() - t0) * 1000, 1)

            if not text:
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "section": section,
                        "content": "No content found for this section.",
                    },
                    execution_time_ms=elapsed,
                )

            # Truncate if extreme, but usually sections are manageable
            preview = text[:5000] + "..." if len(text) > 5000 else text

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "section": section,
                    "content_length": len(text),
                    "content_preview": preview,
                    "full_content": (
                        text if len(text) < 100000 else text[:100000] + "\n[Truncated]"
                    ),
                },
                execution_time_ms=elapsed,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"SEC section extraction failed: {str(e)}",
            )


# ═══════════════════════════════════════════════
#  6. Company Data (NEW — Wikipedia/Wikidata)
# ═══════════════════════════════════════════════


class CompanyDataTool(BaseTool):
    """Look up basic company information from Wikipedia"""

    def __init__(self):
        super().__init__(
            name="company_data",
            description="Look up basic company information — founding year, headquarters, employee count, description — from Wikipedia. Works for well-known companies.",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Company name (e.g., 'Zapier')",
                },
            },
            "required": ["company_name"],
        }

    async def execute(self, company_name: str) -> ToolResult:
        t0 = time.time()
        try:
            import httpx

            # Wikipedia API — search and get extract
            async with httpx.AsyncClient(timeout=10) as client:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": f"{company_name} company",
                        "srlimit": 1,
                        "format": "json",
                    },
                )
                search_data = search_resp.json()
                results = search_data.get("query", {}).get("search", [])

                if not results:
                    return ToolResult(
                        success=True,
                        data={
                            "company": company_name,
                            "found": False,
                            "note": f"No Wikipedia page found for '{company_name}'.",
                        },
                        execution_time_ms=round((time.time() - t0) * 1000, 1),
                    )

                page_title = results[0]["title"]

                # Get full extract
                extract_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": page_title,
                        "prop": "extracts|info",
                        "exintro": True,
                        "explaintext": True,
                        "format": "json",
                    },
                )
                extract_data = extract_resp.json()
                pages = extract_data.get("query", {}).get("pages", {})
                page = next(iter(pages.values()), {})

                extract = page.get("extract", "")[:2000]
                url = f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"

            elapsed = round((time.time() - t0) * 1000, 1)
            return ToolResult(
                success=True,
                data={
                    "company": company_name,
                    "found": True,
                    "wikipedia_title": page_title,
                    "url": url,
                    "summary": extract,
                },
                execution_time_ms=elapsed,
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"Company lookup failed: {str(e)}"
            )


# ═══════════════════════════════════════════════
#  7. Market Data (existing, improved)
# ═══════════════════════════════════════════════


class MarketDataTool(BaseTool):
    """Retrieve market data, industry benchmarks via RAG knowledgebase"""

    def __init__(self):
        super().__init__(
            name="market_data",
            description="Retrieve industry multiples, market sizing, competitor data, and trends from indexed documents",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data_type": {
                    "type": "string",
                    "enum": [
                        "industry_multiples",
                        "market_size",
                        "competitors",
                        "trends",
                    ],
                    "description": "Type of market data to retrieve",
                },
                "industry": {"type": "string", "description": "Industry sector"},
                "region": {
                    "type": "string",
                    "description": "Geographic region",
                    "default": "global",
                },
            },
            "required": ["data_type", "industry"],
        }

    async def execute(
        self, data_type: str, industry: str, region: str = "global"
    ) -> ToolResult:
        try:
            from app.core.memory.pageindex_client import get_pageindex_client

            pageindex = get_pageindex_client()
            query = f"{data_type} for {industry} industry in {region} region"
            results = await pageindex.query(query, top_k=5)
            if results and len(results) > 0:
                return ToolResult(
                    success=True,
                    data={
                        "type": data_type,
                        "industry": industry,
                        "region": region,
                        "source": "pageindex_rag",
                        "documents_found": len(results),
                        "data": {
                            "retrieved_context": [
                                {
                                    "content": r.get("content", ""),
                                    "score": r.get("score", 0),
                                }
                                for r in results[:3]
                            ]
                        },
                    },
                )
        except Exception:
            pass
        return ToolResult(
            success=True,
            data={
                "type": data_type,
                "industry": industry,
                "region": region,
                "source": "no_documents_indexed",
                "data": {
                    "note": f"No {data_type} docs indexed for {industry}. Upload deal documents to enable RAG retrieval."
                },
            },
        )


# ═══════════════════════════════════════════════
#  8. Legal Clause Analyzer (existing)
# ═══════════════════════════════════════════════


class LegalClauseTool(BaseTool):
    """Analyze legal clauses for risks and standard terms"""

    def __init__(self):
        super().__init__(
            name="legal_clause_analyzer",
            description="Analyze legal clauses for risk indicators, standard terms compliance, and suggest improvements",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "clause_text": {
                    "type": "string",
                    "description": "Legal clause text to analyze",
                },
                "clause_type": {
                    "type": "string",
                    "enum": [
                        "indemnification",
                        "termination",
                        "non_compete",
                        "ip_assignment",
                        "warranty",
                    ],
                    "description": "Type of clause",
                },
            },
            "required": ["clause_text", "clause_type"],
        }

    async def execute(self, clause_text: str, clause_type: str) -> ToolResult:
        risk_indicators = [
            "unlimited liability",
            "broad indemnification",
            "perpetual",
            "irrevocable",
            "sole discretion",
        ]
        risk_score = sum(1 for ind in risk_indicators if ind in clause_text.lower())
        return ToolResult(
            success=True,
            data={
                "clause_type": clause_type,
                "risk_score": risk_score,
                "risk_level": (
                    "high" if risk_score > 2 else "medium" if risk_score > 0 else "low"
                ),
                "suggestions": (
                    [
                        "Consider limiting liability",
                        "Add carve-outs",
                        "Set explicit duration",
                    ]
                    if risk_score > 1
                    else []
                ),
            },
        )


# ═══════════════════════════════════════════════
#  9. Report Generation (NEW - Phase 2)
# ═══════════════════════════════════════════════


class ReportGenerationTool(BaseTool):
    """Generate final deliverable reports (PPTX, PDF, Excel)"""

    def __init__(self):
        super().__init__(
            name="generate_report",
            description="Generate a finished McKinsey-style report document (PPTX, PDF, or Excel) based on the synthesized deal data.",
        )

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["pptx", "pdf", "excel"],
                    "description": "The format of the report to generate",
                },
                "deal_context": {
                    "type": "object",
                    "description": "Core deal context information (name, target_company, etc.)",
                },
                "analyst_data": {
                    "type": "object",
                    "description": "Synthesized analysis data to include in the report",
                },
                "agent_results": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Raw results from individual agents to include in the appendix or raw data sheets",
                },
            },
            "required": ["format", "deal_context", "analyst_data", "agent_results"],
        }

    async def execute(
        self,
        format: str,
        deal_context: Dict,
        analyst_data: Dict,
        agent_results: List[Dict],
    ) -> ToolResult:
        try:
            from app.core.reports.report_generator import (
                generate_pptx,
                generate_pdf,
                generate_excel,
            )
            import base64

            if format == "pptx":
                file_bytes = generate_pptx(deal_context, analyst_data, agent_results)
                ext = "pptx"
            elif format == "pdf":
                file_bytes = generate_pdf(deal_context, analyst_data, agent_results)
                ext = "pdf"
            elif format == "excel":
                file_bytes = generate_excel(deal_context, analyst_data, agent_results)
                ext = "xlsx"
            else:
                return ToolResult(
                    success=False, data=None, error=f"Unsupported format: {format}"
                )

            # Return base64 encoded bytes so it can be passed via JSON safely
            encoded = base64.b64encode(file_bytes).decode("utf-8")

            return ToolResult(
                success=True,
                data={
                    "message": f"Successfully generated {format.upper()} report.",
                    "file_extension": ext,
                    "file_bytes_base64": encoded,
                    "size_bytes": len(file_bytes),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"Report generation failed: {str(e)}"
            )


# ═══════════════════════════════════════════════
#  Tool Router (with per-agent routing)
# ═══════════════════════════════════════════════

# Which tools each agent gets access to
AGENT_TOOL_MAP: Dict[str, List[str]] = {
    "financial_analyst": [
        "financial_calculator",
        "document_search",
        "sec_filings",
        "web_search",
        "company_data",
        "peer_discovery",
        "finance_analysis",
        "alpha_vantage",
        "finnhub_data",
        "financial_datasets",
        "filing_due_diligence",
    ],
    "market_researcher": [
        "web_search",
        "web_scraper",
        "market_data",
        "company_data",
        "startup_intelligence",
        "peer_discovery",
        "finnhub_data",
    ],
    "legal_advisor": [
        "legal_clause_analyzer",
        "web_scraper",
        "sec_filings",
        "document_search",
    ],
    "risk_assessor": [
        "web_search",
        "company_data",
        "market_data",
        "filing_due_diligence",
    ],
    "valuation_agent": [
        "financial_calculator",
        "sec_filings",
        "web_search",
        "company_data",
        "fetch_comparable_companies",
        "generate_football_field",
        "run_sensitivity_analysis",
        "fetch_financial_statements",
        "peer_discovery",
        "finance_analysis",
        "alpha_vantage",
        "financial_datasets",
        "run_monte_carlo_irr",
        "filing_due_diligence",
    ],
    "debate_moderator": ["web_search", "company_data"],
    # ── New agents ──
    "ai_tech_diligence_agent": [
        "ai_stack_scanner",
        "model_defensibility_scorer",
        "ai_value_quantifier",
        "document_search",
        "web_search",
        "company_data",
    ],
    "esg_agent": [
        "carbon_footprint_extractor",
        "supply_chain_risk_flagger",
        "esg_scorer",
        "document_search",
        "web_search",
    ],
    "integration_planner_agent": [
        "roadmap_generator",
        "churn_monte_carlo",
        "synergy_tracker",
        "document_search",
    ],
    "advanced_financial_modeler": [
        "financial_calculator",
        "document_search",
        "sec_filings",
        "company_data",
        "fetch_financial_statements",
        "finance_analysis",
        "alpha_vantage",
        "finnhub_data",
        "financial_datasets",
        "filing_due_diligence",
        "run_monte_carlo_irr",
    ],
    "data_curator": [
        "document_search",
        "web_search",
        "company_data",
        "market_data",
        "peer_discovery",
        "finance_analysis",
    ],
    "complex_reasoning": [
        "web_search",
        "document_search",
        "financial_calculator",
        "finance_analysis",
    ],
    "report_architect": ["document_search", "generate_report"],
    "project_manager": ["web_search", "company_data", "startup_intelligence"],
    "dcf_lbo_architect": [
        "financial_calculator",
        "document_search",
        "sec_filings",
        "company_data",
        "excel_model_populate",
        "excel_export_tables",
        "fetch_financial_statements",
        "run_sensitivity_analysis",
        "finance_analysis",
        "financial_datasets",
        "run_monte_carlo_irr",
        "filing_due_diligence",
    ],
    "prospectus_agent": [
        "document_search",
        "sec_filings",
        "web_scraper",
        "company_data",
    ],
    "due_diligence_agent": [
        "web_search",
        "web_scraper",
        "company_data",
        "market_data",
        "startup_intelligence",
        "filing_due_diligence",
    ],
    "investment_memo_agent": [
        "web_search",
        "company_data",
        "document_search",
        "generate_report",
    ],
    "compiler_agent": [
        "generate_report",
    ],
    "treasury_agent": ["financial_calculator", "web_search"],
    "fpa_forecasting_agent": ["financial_calculator", "market_data", "web_search"],
    "tax_compliance_agent": ["web_search", "web_scraper", "document_search"],
    # ── OFAS agents ──
    "ofas_supervisor": [
        "document_search",
        "web_search",
        "company_data",
        "fetch_financial_statements",
    ],
    "business_analyst": ["web_search", "company_data", "document_search"],
    "compliance_qa_agent": [
        "document_search",
        "web_search",
        "cyber_vuln_scanner",
        "antitrust_hhi_calculator",
        "privacy_auditor",
    ],
}


class ToolRouter:
    """Routes tool calls to appropriate tools with per-agent filtering"""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.logger = structlog.get_logger()

    def register_tool(self, tool: BaseTool):
        self.tools[tool.name] = tool
        self.logger.info("Registered tool", tool_name=tool.name)

    def register_default_tools(self, pageindex_client=None):
        """Register all tools"""
        self.register_tool(FinancialCalculatorTool())
        self.register_tool(DuckDuckGoSearchTool())
        self.register_tool(WebScraperTool())
        self.register_tool(SECFilingsTool())
        self.register_tool(CompanyDataTool())
        self.register_tool(MarketDataTool())
        self.register_tool(LegalClauseTool())
        self.register_tool(ReportGenerationTool())
        # Startup intelligence (Crunchbase/BrightData scraping)
        try:
            from app.core.tools.startup_intelligence_tool import StartupIntelligenceTool

            self.register_tool(StartupIntelligenceTool())
        except ImportError:
            self.logger.warning("StartupIntelligenceTool import failed")

        if pageindex_client:
            self.register_tool(DocumentSearchTool(pageindex_client))

        # Financial Data Integrations (FinanceDatabase & FinanceToolkit)
        try:
            from app.core.tools.finance_database_tool import PeerDiscoveryTool

            self.register_tool(PeerDiscoveryTool())
        except ImportError:
            self.logger.warning("PeerDiscoveryTool import failed")

        try:
            from app.core.tools.finance_toolkit_tool import FinanceAnalysisTool

            self.register_tool(FinanceAnalysisTool())
        except ImportError:
            self.logger.warning("FinanceAnalysisTool import failed")

        # Additional API Integrations (Finnhub, Alpha Vantage, Financial Datasets)
        try:
            from app.core.tools.alpha_vantage_tool import AlphaVantageTool

            self.register_tool(AlphaVantageTool())
        except ImportError:
            self.logger.warning("AlphaVantageTool import failed")

        try:
            from app.core.tools.finnhub_tool import FinnhubTool

            self.register_tool(FinnhubTool())
        except ImportError:
            self.logger.warning("FinnhubTool import failed")

        try:
            from app.core.tools.financial_datasets_tool import FinancialDatasetsTool

            self.register_tool(FinancialDatasetsTool())
        except ImportError:
            self.logger.warning("FinancialDatasetsTool import failed")

        # OFAS tools — Excel Model Engine + Financial Data API
        try:
            from app.core.tools.excel_model_engine import (
                ExcelModelPopulateTool,
                ExcelExportTablesTool,
            )

            self.register_tool(ExcelModelPopulateTool())
            self.register_tool(ExcelExportTablesTool())
        except ImportError:
            self.logger.warning("OFAS ExcelModelEngine import failed")

        try:
            from app.core.tools.financial_data_api import FetchFinancialStatementsTool

            self.register_tool(FetchFinancialStatementsTool())
        except ImportError:
            self.logger.warning("OFAS FetchFinancialStatements import failed")

        # Phase 2 — Valuation tools
        try:
            from app.core.tools.valuation_tools import (
                FetchComparableCompaniesTool,
                GenerateFootballFieldTool,
                RunSensitivityAnalysisTool,
                RunMonteCarloIRRTool,
            )

            self.register_tool(FetchComparableCompaniesTool())
            self.register_tool(GenerateFootballFieldTool())
            self.register_tool(RunSensitivityAnalysisTool())
            self.register_tool(RunMonteCarloIRRTool())
        except ImportError as e:
            self.logger.warning(f"Valuation tools import failed: {e}")

        # Phase 2 — Tech Diligence tools
        try:
            from app.core.tools.ai_tech_tools import (
                AIStackScannerTool,
                ModelDefensibilityScorerTool,
                AIValueQuantifierTool,
            )

            self.register_tool(AIStackScannerTool())
            self.register_tool(ModelDefensibilityScorerTool())
            self.register_tool(AIValueQuantifierTool())
        except ImportError:
            self.logger.warning("OFAS AITechTools import failed")

        # Phase 2 — ESG tools
        try:
            from app.core.tools.esg_tools import (
                CarbonFootprintExtractorTool,
                SupplyChainRiskFlaggerTool,
                ESGScorerTool,
            )

            self.register_tool(CarbonFootprintExtractorTool())
            self.register_tool(SupplyChainRiskFlaggerTool())
            self.register_tool(ESGScorerTool())
        except ImportError:
            self.logger.warning("OFAS ESGTools import failed")

        # Phase 3 — Regulatory & Cyber tools
        try:
            from app.core.tools.regulatory_tools import (
                CyberVulnScannerTool,
                AntitrustHHICalculatorTool,
                PrivacyAuditorTool,
            )

            self.register_tool(CyberVulnScannerTool())
            self.register_tool(AntitrustHHICalculatorTool())
            self.register_tool(PrivacyAuditorTool())
        except ImportError:
            self.logger.warning("OFAS RegulatoryTools import failed")

        # Phase 3 — Integration tools
        try:
            from app.core.tools.integration_tools import (
                RoadmapGeneratorTool,
                ChurnMonteCarloTool,
                SynergyTrackerTool,
            )

            self.register_tool(RoadmapGeneratorTool())
            self.register_tool(ChurnMonteCarloTool())
            self.register_tool(SynergyTrackerTool())
        except ImportError:
            self.logger.warning("OFAS IntegrationTools import failed")

        # Phase 5 — Filing Due Diligence (NLP change detection)
        try:
            from app.core.tools.filing_due_diligence import FilingDueDiligenceTool

            self.register_tool(FilingDueDiligenceTool())
        except ImportError:
            self.logger.warning("FilingDueDiligenceTool import failed")

        # Phase 4 — Reporting tools
        try:
            from app.core.tools.reporting_tools import (
                GenerateICMemoTool,
                GenerateDealDeckTool,
            )

            self.register_tool(GenerateICMemoTool())
            self.register_tool(GenerateDealDeckTool())
        except ImportError:
            self.logger.warning("OFAS ReportingTools import failed")

    def list_tools(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get tool schemas, optionally filtered for a specific agent"""
        if agent_name and agent_name in AGENT_TOOL_MAP:
            allowed = AGENT_TOOL_MAP[agent_name]
            return [
                tool.get_schema()
                for name, tool in self.tools.items()
                if name in allowed
            ]
        return [tool.get_schema() for tool in self.tools.values()]

    async def execute(self, tool_name: str, params: Any) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(
                success=False, data=None, error=f"Tool '{tool_name}' not found"
            )

        # Ensure params is a dict (LLMs sometimes send a JSON string)
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Invalid JSON in tool arguments: {params}",
                )

        tool = self.tools[tool_name]
        try:
            self.logger.info(
                "Executing tool", tool_name=tool_name, params_keys=list(params.keys())
            )
            result = await tool.execute(**params)
            self.logger.info(
                "Tool execution complete",
                tool_name=tool_name,
                success=result.success,
                time_ms=result.execution_time_ms,
            )

            # ── Provenance capture (QA Flow 6) ──
            pctx = getattr(self, "_provenance_context", None)
            if pctx and pctx.get("deal_id"):
                try:
                    from app.core.provenance import get_provenance_collector

                    provenance_id = await get_provenance_collector().record_tool_call(
                        deal_id=pctx["deal_id"],
                        agent_name=pctx.get("agent_name", "unknown"),
                        tool_name=tool_name,
                        params=params,
                        result=(
                            result.data if result.success else {"error": result.error}
                        ),
                        execution_round=pctx.get("execution_round", 1),
                    )
                    result.provenance_id = provenance_id
                except Exception as e:
                    self.logger.warning("provenance_capture_failed", error=str(e))

            return result
        except Exception as e:
            self.logger.error(
                "Tool execution failed", tool_name=tool_name, error=str(e)
            )
            return ToolResult(success=False, data=None, error=str(e))

    def set_provenance_context(
        self, deal_id: str, agent_name: str, execution_round: int = 1
    ):
        """Set provenance capture context for subsequent tool executions."""
        self._provenance_context = {
            "deal_id": deal_id,
            "agent_name": agent_name,
            "execution_round": execution_round,
        }

    def clear_provenance_context(self):
        """Clear provenance context after agent finishes."""
        self._provenance_context = None

    async def execute_function_calls(
        self, function_calls: List[Dict]
    ) -> List[ToolResult]:
        results = []
        for call in function_calls:
            result = await self.execute(call["name"], call.get("args", {}))
            results.append(result)
        return results
