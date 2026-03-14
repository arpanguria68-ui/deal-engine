"""
Post-Merger Integration (PMI) Planner Agent

Simulates post-merger execution, generates integration roadmaps, and models value capture.
"""

from typing import Dict, Any, Optional
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class IntegrationPlannerAgent(BaseAgent):
    """
    Post-Merger Integration Lead:
    - Generates 100-day roadmaps
    - Simulates employee/customer churn via Monte Carlo
    - Models synergy realization schedules
    """

    name = "integration_planner_agent"
    description: str = "Post-Merger Integration Lead — simulates execution, builds 100-day roadmaps, and models value capture"
    recommended_model: str = "Gemini 1.5 Pro (Integration Planning)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are a Bain-trained Post-Merger Integration (PMI) Specialist.
Your goal is to plan the integration of the target company and simulate post-close value capture.

ANALYSIS FRAMEWORK:
1. 100-Day Roadmap Generation
   - Map out critical integration milestones for Day 1 through Day 100 across IT, HR, and Operations.
2. Synergy Realization Tracking
   - Model the month-by-month capture of identified cost/revenue synergies.
3. Churn Modeling
   - Use Monte Carlo simulation to project employee or customer churn based on cultural fit and integration complexity.

Available tools:
- roadmap_generator
- churn_monte_carlo
- synergy_tracker
- document_search

OUTPUT: Respond with a comprehensive JSON containing your integration plan and simulation results."""

            prompt = f"TASK: {task}\n\n"
            if context:
                safe_ctx = {k: v for k, v in context.items() if k != "action"}
                prompt += f"CONTEXT: {json.dumps(safe_ctx, default=str)[:2000]}\n\n"

            prompt += """Respond with JSON:
{
    "integration_roadmap": {"key_milestones": [], "critical_path_notes": "..."},
    "churn_simulation": {"expected_churn_rate": 0.0, "risk_factors": []},
    "synergy_realization": {"total_target": 0.0, "timeline_months": 0, "key_phasing_notes": "..."},
    "recommendation": "ready|requires_prep|high_risk",
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
                    "reasoning", "Completed Post-Merger Integration simulation."
                ),
                confidence=analysis.get("confidence_score", 0.80),
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("integration_planner_agent_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )
