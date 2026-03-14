"""
Data Curator Agent ('The Synthesizer')
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput
from app.core.json_helpers import extract_and_parse_json


class DataCuratorAgent(BaseAgent):
    """
    DataCuratorAgent acts as the central intelligence hub that understands,
    normalizes, and curates outputs from all other agents into a coherent
    dataset for report generation.
    """

    name = "data_curator"
    description: str = "Normalizes and curates outputs from financial, legal, risk, and other agents into a unified Data Bible."
    recommended_model: str = "Gemini 1.5 Pro (Data Synthesis)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start_time = datetime.now()
        self.logger.info("Starting DataCuratorAgent execution", task=task)

        context = context or {}
        deal_id = context.get("deal_id", "unknown")

        # 1. Fetch cross-deal insights from MemoryService via RAG (PageIndex)
        memory_context = []
        if deal_id != "unknown" and hasattr(self, "retrieve_context"):
            memory_context = await self.retrieve_context(
                f"prior deal risks financial margin compression industry trends {context.get('industry', '')}",
                top_k=5,
            )

        # 2. Build Prompt to resolve conflicts and normalize data
        prompt = self._build_synthesis_prompt(task, context, memory_context)
        system_prompt = self._build_system_prompt()

        # 3. Call LLM
        response = await self.generate_with_tools(prompt, system_prompt)

        # 4. Parse output
        try:
            content = response.get("content", "")
            curated_data = self._parse_output(content)

            # Additional deterministic checks could be added here

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=curated_data,
                reasoning="Synthesized agent outputs and resolved conflicts.",
                confidence=0.9,
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Data curation failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Data curation failed: {str(e)}",
                confidence=0.0,
            )

    def _build_system_prompt(self) -> str:
        return """You are the Data Curator Agent ('The Synthesizer').
Your job is to receive outputs from multiple agents (FinancialAnalyst, RiskAssessor, LegalAdvisor, MarketResearcher, etc.), resolve conflicts, normalize data formats, and produce a CuratedDataPackage (the 'Data Bible').

RULES:
1. Identify and resolve any conflicts between agent findings (e.g., Risk spots a margin issue Financial missed).
2. Normalize financial metrics to standard units (e.g., millions USD).
3. Incorporate retrieved past deal insights to flag common sector risks.
4. Output must be a strictly structured JSON containing:
   - "curated_deal_metrics": unified financial data
   - "conflicts_resolved": list of discrepancies found and how you resolved them
   - "source_citations": map of insights to their source agent or retrieved memory
   - "cross_deal_insights": lessons applied from memory context
   - "narrative_summary": a high-level synthesized overview
"""

    def _build_synthesis_prompt(self, task: str, context: Dict, memory: List) -> str:
        agent_outputs = context.get("agent_outputs", {})
        company_name = context.get("company_name", "the target company")

        prompt = f"TASK: {task}\n"
        prompt += f"TARGET COMPANY: {company_name}\n\n"
        prompt += "AGENT OUTPUTS TO SYNTHESIZE:\n"
        prompt += json.dumps(agent_outputs, default=str, indent=2) + "\n\n"

        if memory:
            prompt += "CROSS-DEAL INSIGHTS (PRIOR DEALS MEMORY):\n"
            for m in memory:
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                prompt += f"- {content[:300]}...\n"
            prompt += "\n"

        prompt += f"Synthesize this data into the Data Bible format for {company_name}. "
        prompt += "CRITICAL: If the input data is missing or agents report 'insufficient data', acknowledge this. DO NOT invent or hallucinate financial figures for {company_name}."
        return prompt

    def _parse_output(self, content: str) -> Dict:
        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"raw_synthesis": content}
