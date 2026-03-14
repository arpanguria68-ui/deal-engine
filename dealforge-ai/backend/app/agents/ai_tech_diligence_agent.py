"""
AI / Tech Diligence Agent

Assesses a target's AI/ML stack, quantifies tech value creation, and flags IP/vendor risks.
"""

from typing import Dict, Any, Optional
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class AITechDiligenceAgent(BaseAgent):
    """
    AI/Tech Diligence Specialist:
    - Scans AI tech stacks
    - Scores model defensibility
    - Quantifies AI revenue uplift potential
    """

    name = "ai_tech_diligence_agent"
    description: str = "AI and tech diligence — tech stack scanning, model defensibility, and AI value quantification"
    recommended_model: str = "Gemini 1.5 Pro (Technical Architecture)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are an Ex-Google AI researcher turned M&A Consultant.
Your goal is to evaluate the Target Company's machine learning and broader technical stack.

ANALYSIS FRAMEWORK:
1. Tech Stack Overview
   - Extract models, frameworks, infrastructure, and databases 
   - Identify modern components (e.g., RAG, LLMs, Vector DBs) vs legacy systems
2. Model Defensibility
   - Score the IP protection, scalability, and obsolescence risk
   - Highlight critical vendor lock-in or infrastructure risks
3. AI Value Quantification
   - Estimate the potential AI-driven revenue uplift

Available tools:
- ai_stack_scanner
- model_defensibility_scorer
- ai_value_quantifier
- document_search
- web_search

OUTPUT: Respond with a comprehensive JSON containing your findings."""

            prompt = f"TASK: {task}\n\n"
            if context:
                safe_ctx = {k: v for k, v in context.items() if k != "action"}
                prompt += f"CONTEXT: {json.dumps(safe_ctx, default=str)[:2000]}\n\n"

            prompt += """Respond with JSON:
{
    "tech_stack_summary": {"description": "...", "modern_rating": "high|medium|low"},
    "defensibility_assessment": {"score": 0, "key_risks": []},
    "value_quantification": {"uplift_potential_range": "...", "base_uplift": 0},
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
                    "reasoning", "Completed AI/Tech Diligence assessment."
                ),
                confidence=analysis.get("confidence_score", 0.80),
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("ai_tech_diligence_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )
