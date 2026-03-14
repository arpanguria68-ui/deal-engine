"""
Report Architect Agent
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput
from app.core.json_helpers import extract_and_parse_json


class ReportArchitectAgent(BaseAgent):
    """
    Selects and configures report templates based on deal type, audience,
    and customization preferences.
    """

    name = "report_architect"
    description: str = (
        "Configures report templates, visual component manifest, and layout rules."
    )
    recommended_model: str = "Gemini 1.5 Pro (High-Fidelity Synthesis)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start_time = datetime.now()
        self.logger.info("Starting ReportArchitectAgent execution", task=task)

        context = context or {}
        deal_id = context.get("deal_id", "unknown")

        memory_context = []
        if deal_id != "unknown" and hasattr(self, "retrieve_context"):
            memory_context = await self.retrieve_context(
                f"previous report templates industry {context.get('industry', '')} audience {context.get('audience', '')}",
                top_k=3,
            )

        prompt = self._build_prompt(task, context, memory_context)
        system_prompt = self._build_system_prompt()

        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            content = response.get("content", "")
            blueprint = self._parse_output(content)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=blueprint,
                reasoning="Generated report configuration blueprint.",
                confidence=0.9,
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Report architecture failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Report architecture failed: {str(e)}",
                confidence=0.0,
            )

    def _build_system_prompt(self) -> str:
        return """You are the Report Architect Agent. Based on the target audience, deal type, and industry context, you select the appropriate report blueprint.
You define sections, styling flags, and the visual component manifest (which charts to generate).

OUTPUT JSON FORMAT:
{
  "report_type": "IC_Memo", 
  "branding_config": {
      "primary_color": "#003366",
      "font": "Helvetica"
  },
  "sections": [
      {"name": "Executive Summary", "depth": "high"},
      {"name": "Investment Thesis", "depth": "high"},
      {"name": "Risks & Mitigants", "depth": "medium"}
  ],
  "visual_component_manifest": [
      "ebitda_waterfall",
      "wacc_breakdown",
      "driver_sensitivity_tornado"
  ]
}
"""

    def _build_prompt(self, task: str, context: Dict, memory: List) -> str:
        company_name = context.get("company_name", "the target company")
        prompt = f"TASK: {task}\n"
        prompt += f"TARGET COMPANY: {company_name}\n"
        prompt += "CONTEXT:\n"
        prompt += f"Dealer Industry: {context.get('industry', 'General')}\n"
        prompt += f"Report Target Audience: {context.get('audience', 'Investment Committee')}\n\n"

        if memory:
            prompt += "PREVIOUS REPORT ARCHITECTURES ALIGNED TO THIS CONTEXT:\n"
            for m in memory:
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                prompt += f"- {content[:300]}...\n"
            prompt += "\n"

        prompt += f"Create the report blueprint for {company_name}. "
        prompt += "CRITICAL: Based ONLY on the available context. If data is sparse, adapt the blueprint accordingly without making up company facts."
        return prompt

    def _parse_output(self, content: str) -> Dict:
        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"raw_blueprint": content}
