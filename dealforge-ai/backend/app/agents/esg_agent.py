"""
ESG & Sustainability Expert Agent

Quantifies ESG risks, extracts carbon footprints, and estimates green synergy potential.
"""

from typing import Dict, Any, Optional
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class ESGAgent(BaseAgent):
    """
    ESG & Sustainability Expert:
    - Extracts Scope 1/2/3 carbon footprint
    - Flags supply chain / forced labor risks
    - Generates MSCI-style ESG rating and NPV carbon tax impact
    """

    name = "esg_agent"
    description: str = "ESG and sustainability diligence — carbon footprint extraction, supply chain risk flagging, and ESG scoring"
    recommended_model: str = "Gemini 1.5 Pro (ESG Compliance)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are a CSRD-certified Sustainability Analyst and ESG Expert.
Your goal is to evaluate the Target Company's environmental, social, and governance footprint.

ANALYSIS FRAMEWORK:
1. Carbon Footprint
   - Use the extraction tool to detect Scope 1, 2, and 3 emissions from the target's sustainability summary.
2. Supply Chain Risk
   - Evaluate any ethical or forced-labor risks tied to the target's supplier ecosystem.
3. Overarching ESG Score
   - Compute the target's aggregate MSCI-style score and quantify a simulated financial carbon tax impact in USD.

Available tools:
- carbon_footprint_extractor
- supply_chain_risk_flagger
- esg_scorer
- document_search
- web_search

OUTPUT: Respond with a comprehensive JSON containing your ESG diligence findings."""

            prompt = f"TASK: {task}\n\n"
            if context:
                safe_ctx = {k: v for k, v in context.items() if k != "action"}
                prompt += f"CONTEXT: {json.dumps(safe_ctx, default=str)[:2000]}\n\n"

            prompt += """Respond with JSON:
{
    "carbon_footprint": {"total_tco2e": 0, "risk_level": "...", "breakdown": {}},
    "supply_chain_risks": {"severity": "...", "identified_flags": []},
    "esg_scoring": {"composite_score": 0.0, "msci_rating": "...", "carbon_tax_exposure": "..."},
    "recommendation": "proceed|caution|reject",
    "confidence_score": 0.8,
    "reasoning": "..."
}"""

            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")

            from app.core.json_helpers import extract_and_parse_json

            analysis = extract_and_parse_json(content) or {"analysis": content}

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=analysis,
                reasoning=analysis.get(
                    "reasoning", "Completed ESG & Sustainability assessment."
                ),
                confidence=analysis.get("confidence_score", 0.80),
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("esg_agent_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )
