import json
from typing import Dict, Any, List
from app.agents.base import BaseAgent, AgentOutput


class BusinessAnalystAgent(BaseAgent):
    """
    McKinsey Business Analyst Agent
    Specializes in synthesizing raw agent outputs into highly-structured,
    consulting-grade presentations (SCQA frameworks, MECE analysis).
    """

    name = "business_analyst"
    description: str = "Synthesizes raw deal analysis into McKinsey-style executive reports with SCQA and MECE formatting."
    recommended_model: str = "Gemini 1.5 Pro (Unit Economics)"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.system_prompt = """
        You are a top-tier McKinsey Engagement Manager specializing in M&A Due Diligence.
        Your task is to take the raw, unstructured findings from various specialized agents (Financial, Legal, Risk, Market) and synthesize them into a highly-structured, executive-level presentation payload.

        You must use the SCQA framework (Situation, Complication, Question, Answer) for the Executive Summary.
        You must ensure all analysis is MECE (Mutually Exclusive, Collectively Exhaustive).

        OUTPUT INSTRUCTIONS:
        You MUST return ONLY a valid JSON object with the exact structure below. Do NOT output any markdown blocks (```json), just the raw JSON.

        {
            "executive_summary": {
                "situation": "Current state of the target and market...",
                "complication": "The critical issues or risks discovered...",
                "question": "The core strategic question for the acquirer...",
                "answer": "Your synthesized high-level recommendation..."
            },
            "key_takeaways": [
                {
                    "title": "Strong Revenue Growth but Squeezed Margins",
                    "description": "Details supporting the takeaway..."
                },
                ... (exactly 3-4 key takeaways)
            ],
            "financial_synthesis": {
                "narrative": "A polished paragraph summarizing financial viability...",
                "key_metrics": {
                    "Revenue ($M)": 150.0,
                    "EBITDA ($M)": 30.0,
                    "Growth Rate (%)": "15%"
                }
            },
            "risk_matrix": [
                {
                    "category": "Operational",
                    "severity": "High",
                    "mitigation_strategy": "Plan to fix..."
                },
                ...
            ],
            "action_items": [
                "1. Initial action...",
                "2. Second action..."
            ]
        }
        """

    async def run(self, task: str, context=None) -> AgentOutput:
        """Execute agent task (required by BaseAgent abstract method)"""
        import time

        start = time.time()
        result = await self._execute_task(task, context or {})
        result.execution_time_ms = (time.time() - start) * 1000
        return result

    async def _execute_task(self, task: str, context: Dict[str, Any]) -> AgentOutput:
        """Execute the report formatting and synthesis"""

        # Gather all previous agent outputs from context
        agent_data = context.get("deal_data", {})

        prompt = f"""
        TASK: Synthesize the following Deal Analysis into a McKinsey-grade executive summary JSON block.
        DEAL ID: {context.get("deal_id")}
        
        RAW FINDINGS:
        {json.dumps(agent_data, indent=2)}
        
        Using the System Prompt instructions, generate the strict JSON payload.
        """

        try:
            # We enforce JSON output directly from the LLM endpoint or by pure parsing
            result = await self.llm.generate(prompt, self.system_prompt)
            data = self._parse_json_result(result)

            return AgentOutput(
                success=True,
                data=data,
                reasoning="Synthesized agent outputs into a McKinsey-style SCQA structured JSON payload.",
            )
        except Exception as e:
            self.logger.error("Business Analyst synthesis failed", error=str(e))
            return AgentOutput(
                success=False,
                data={"error": str(e)},
                reasoning=f"Failed to generate structured synthesis: {str(e)}",
            )

    def _parse_json_result(self, result: Any) -> Dict[str, Any]:
        """Parse JSON response from LLM, handling potential markdown blocks."""
        content = (
            result.get("content", "").strip()
            if isinstance(result, dict)
            else str(result)
        )

        # Strip markdown code blocks if present
        if content.startswith("```"):
            import re

            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if match:
                content = match.group(1)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Fallback for partial/corrupted JSON
            self.logger.warning(
                "failed_to_parse_ba_json", content_snippet=content[:100]
            )
            return {}
