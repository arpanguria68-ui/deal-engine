"""
Complex Reasoning Agent (Chain-of-Thought)
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput
from app.core.json_helpers import extract_and_parse_json


class ComplexReasoningAgent(BaseAgent):
    """
    ComplexReasoningAgent runs explicit multi-step reasoning to detect logical
    fallacies, ensure conclusions follow from premises, and produce a
    ConfidenceWeightedRecommendation.
    """

    name = "complex_reasoning"
    description: str = "Provides explicit multi-step reasoning for investment recommendations via Chain-of-Thought."
    recommended_model: str = "Gemini 1.5 Pro (Chain-of-Thought)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start_time = datetime.now()
        self.logger.info("Starting ComplexReasoningAgent execution", task=task)

        context = context or {}
        curated_data = context.get("curated_data", {})
        deal_id = context.get("deal_id", "unknown")

        memory_context = []
        if deal_id != "unknown" and hasattr(self, "retrieve_context"):
            memory_context = await self.retrieve_context(
                f"risk factors reasoning logic fallback {task}",
                top_k=3,
            )

        prompt = self._build_prompt(task, curated_data, memory_context, context)
        system_prompt = self._build_system_prompt()

        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            content = response.get("content", "")
            reasoning_trace = self._parse_output(content)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=reasoning_trace,
                reasoning="Executed CoT reasoning successfully.",
                confidence=0.95,
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Complex reasoning failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Complex reasoning failed: {str(e)}",
                confidence=0.0,
            )

    def _build_system_prompt(self) -> str:
        return """You are the Complex Reasoning Agent. Your role is to apply rigorous Chain-of-Thought logic to the CuratedDataPackage.
You must construct logical bridges from premise -> evidence -> inference -> conclusion.
Ensure you strictly separate facts from assumptions and identify logical fallacies.

OUTPUT JSON FORMAT:
{
  "reasoning_trace": [
     {"step": 1, "premise": "...", "evidence": "...", "inference": "..."}
  ],
  "logical_gaps_flagged": ["gap 1", "gap 2"],
  "assumption_register": ["assumption 1", "assumption 2"],
  "confidence_weighted_recommendation": {
     "recommendation": "PROCEED / HOLD / REJECT",
     "confidence_score": 0.85,
     "rationale": "..."
  }
}
"""

    def _build_prompt(self, task: str, curated_data: Dict, memory: List, context: Dict = None) -> str:
        company_name = context.get("company_name", "the target company") if context else "the target company"
        prompt = f"TASK: {task}\n"
        prompt += f"TARGET COMPANY: {company_name}\n"
        prompt += "CURATED DATA BIBLE:\n"
        prompt += json.dumps(curated_data, default=str, indent=2) + "\n\n"

        if memory:
            prompt += "PRIOR DEAL REASONING CONTEXT:\n"
            for m in memory:
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                prompt += f"- {content[:300]}...\n"
            prompt += "\n"

        prompt += f"Apply Chain-of-Thought reasoning to arrive at a final investment recommendation for {company_name}. "
        prompt += "CRITICAL: If the Curated Data Bible is empty or contains placeholders, acknowledge the lack of data. DO NOT hallucinate facts."
        return prompt

    def _parse_output(self, content: str) -> Dict:
        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"raw_reasoning": content}
