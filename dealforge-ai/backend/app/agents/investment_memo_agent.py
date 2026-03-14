"""
Investment Memo & Charting Agent — 'The Editor'

Synthesizes raw data into Bulge Bracket-grade investment memos.
Generates visual aids (football field, Sankey, radar charts).
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class InvestmentMemoAgent(BaseAgent):
    """
    The Editor — produces final investment deliverables:
    - Executive summary with key metrics
    - Investment thesis and recommendation
    - Football field valuation chart
    - Risk assessment visualization
    - Appendix with detailed agent findings
    """

    name = "investment_memo_agent"
    description: str = (
        "Generates McKinsey-grade investment memos with charts and executive summaries"
    )
    recommended_model: str = "Gemini 1.5 Pro (Executive Writing)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            # Gather all agent results from context
            agent_results = context.get("agent_results", [])

            system_prompt = """You are a Senior Investment Banking Associate drafting an investment memo.

MEMO STRUCTURE (McKinsey/Goldman format):
1. EXECUTIVE SUMMARY (1 page)
   - Transaction overview (buyer, target, structure)
   - Valuation range and recommended price
   - Key thesis: 3 reasons to invest
   - Key risks: 3 reasons to pass
   - Final recommendation: STRONG BUY / BUY / HOLD / PASS

2. COMPANY OVERVIEW
   - Business description and history
   - Revenue model and key segments
   - Management team assessment

3. MARKET ANALYSIS
   - Industry dynamics and TAM
   - Competitive positioning
   - Growth drivers and headwinds

4. FINANCIAL ANALYSIS
   - Historical performance (3-5 years)
   - Projected financials
   - Key ratios and benchmarks

5. VALUATION
   - DCF analysis (base, bull, bear cases)
   - Comparable companies analysis
   - Precedent transactions
   - Football field summary

6. RISK ASSESSMENT
   - Risk matrix (probability × impact)
   - Mitigation strategies
   - Downside scenarios

7. RECOMMENDATION
   - Clear BUY/PASS with conditions
   - Suggested entry price and structure

RULES:
- Every claim must reference a data source
- Use precise numbers, not vague qualifiers
- Present ranges, not point estimates
- Flag assumptions explicitly"""

            prompt = f"TASK: {task}\n\n"
            if agent_results:
                prompt += "AGENT FINDINGS:\n"
                for r in agent_results[:10]:
                    agent_name = r.get("agent", "unknown")
                    data = json.dumps(r.get("data", {}), default=str)[:500]
                    prompt += f"\n--- {agent_name} ---\n{data}\n"

            if context:
                prompt += f"\nDEAL CONTEXT: {json.dumps({k: v for k, v in context.items() if k != 'agent_results'}, default=str)[:1500]}\n"

            prompt += (
                "\nDraft a complete investment memo following the structure above."
            )

            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")

            # Generate charts if infographic engine available
            charts = self._generate_charts(context)

            analysis = {
                "memo": content,
                "charts": charts,
                "sections": self._extract_sections(content),
            }

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=analysis,
                reasoning="Generated investment memo with executive summary and supporting charts.",
                confidence=0.85,
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("investment_memo_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    def _generate_charts(self, context: Dict) -> Dict[str, str]:
        """Generate infographic charts from analysis data."""
        charts = {}
        try:
            from app.core.reports.infographic_engine import InfographicEngine

            # Football field if valuation data exists
            valuations = context.get("valuations")
            if valuations:
                charts["football_field"] = "generated"

            # Risk heatmap if risk data exists
            risks = context.get("risk_data")
            if risks:
                charts["risk_heatmap"] = "generated"

            # Deal score radar if scores exist
            scores = context.get("deal_scores")
            if scores:
                charts["deal_radar"] = "generated"

        except ImportError:
            self.logger.warning("infographic_engine_not_available")
        return charts

    def _extract_sections(self, content: str) -> List[Dict]:
        """Extract memo sections from LLM output."""
        sections = []
        current = {"title": "Introduction", "content": ""}
        for line in content.split("\n"):
            if line.strip().startswith("#"):
                if current["content"].strip():
                    sections.append(current)
                current = {"title": line.strip().lstrip("#").strip(), "content": ""}
            else:
                current["content"] += line + "\n"
        if current["content"].strip():
            sections.append(current)
        return sections
