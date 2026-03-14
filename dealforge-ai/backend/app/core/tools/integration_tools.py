"""
Post-Merger Integration (PMI) Tools for DealForge AI.

Specialized tools to generate 100-day roadmaps, simulate churn via Monte Carlo,
and track synergy realization phases.
"""

from typing import Dict, Any, List, Optional
import structlog
import random
import math
from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class RoadmapGeneratorTool(BaseTool):
    """Generates a risk-weighted 100-day integration plan."""

    def __init__(self):
        super().__init__(
            name="roadmap_generator",
            description=(
                "Generates a structured 100-day post-merger integration plan with "
                "key milestones for IT, HR, and Brand Transition."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "Name of the target company being integrated.",
                },
                "complexity_level": {
                    "type": "string",
                    "description": "Integration complexity (Low, Medium, High). Default is Medium.",
                },
            },
            "required": ["company_name"],
        }

    async def execute(
        self, company_name: str = "Target", complexity_level: str = "Medium", **kwargs
    ) -> ToolResult:

        # Base roadmap structure
        roadmap = [
            {
                "day": "Day 1",
                "stream": "Corporate",
                "milestone": "Legal Day 1 execution, Townhall announcement",
            },
            {
                "day": "Day 14",
                "stream": "HR",
                "milestone": "Harmonize core employee benefits and payroll systems",
            },
            {
                "day": "Day 30",
                "stream": "IT",
                "milestone": "Initial email/SSO migration complete",
            },
            {
                "day": "Day 60",
                "stream": "Sales",
                "milestone": "Cross-training on combined product portfolio",
            },
            {
                "day": "Day 90",
                "stream": "Operations",
                "milestone": "Consolidation of overlapping back-office functions",
            },
            {
                "day": "Day 100",
                "stream": "Corporate",
                "milestone": "100-Day review, synergy capture assessment",
            },
        ]

        if complexity_level.lower() == "high":
            roadmap.insert(
                2,
                {
                    "day": "Day 21",
                    "stream": "IT",
                    "milestone": "Complex ERP system mapping and interim bridge rollout",
                },
            )
            roadmap.insert(
                5,
                {
                    "day": "Day 75",
                    "stream": "Brand",
                    "milestone": "Legacy brand sunset and migration to master brand",
                },
            )

        return ToolResult(
            success=True,
            data={
                "target_company": company_name,
                "integration_complexity": complexity_level,
                "milestone_roadmap": roadmap,
                "critical_path_duration_days": 100,
            },
        )


class ChurnMonteCarloTool(BaseTool):
    """Simulates employee/customer churn post-merger via Monte Carlo."""

    def __init__(self):
        super().__init__(
            name="churn_monte_carlo",
            description=(
                "Simulates expected employee or customer churn over 12 months using a "
                "Monte Carlo approach based on cultural fit and starting headcount."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "base_count": {
                    "type": "number",
                    "description": "Starting headcount or customer count.",
                },
                "cultural_fit_score": {
                    "type": "number",
                    "description": "Cultural fit score from 0 to 100 (higher means better fit).",
                },
                "iterations": {
                    "type": "integer",
                    "description": "Number of Monte Carlo paths to run (default 1000).",
                },
            },
            "required": ["base_count", "cultural_fit_score"],
        }

    async def execute(
        self,
        base_count: float = 0.0,
        cultural_fit_score: float = 50.0,
        iterations: int = 1000,
        **kwargs
    ) -> ToolResult:
        if base_count <= 0:
            return ToolResult(success=False, data=None, error="base_count must be > 0")

        iterations = min(10000, max(100, iterations))

        # Determine average expected annual churn base rate
        # Suppose a perfect fit = 5% baseline churn, awful fit = 30% churn
        expected_churn_rate = 0.30 - (0.25 * (cultural_fit_score / 100.0))

        results = []
        for _ in range(iterations):
            # Beta distribution around the expected mean
            # Using random.triangular for simplicity (low, high, mode)
            mode = expected_churn_rate
            low = max(0.0, mode - 0.10)
            high = min(1.0, mode + 0.15)

            simulated_rate = random.triangular(low, high, mode)
            results.append(simulated_rate)

        avg_rate = sum(results) / iterations
        p10 = sorted(results)[int(0.10 * iterations)]
        p90 = sorted(results)[int(0.90 * iterations)]

        expected_churned_count = int(base_count * avg_rate)

        return ToolResult(
            success=True,
            data={
                "base_count": base_count,
                "expected_annual_churn_rate": round(avg_rate, 4),
                "churn_rate_p10": round(p10, 4),
                "churn_rate_p90": round(p90, 4),
                "expected_churned_count": expected_churned_count,
                "retained_count": int(base_count - expected_churned_count),
            },
        )


class SynergyTrackerTool(BaseTool):
    """Models phased synergy realization using an OU-inspired fade."""

    def __init__(self):
        super().__init__(
            name="synergy_tracker",
            description=(
                "Models how estimated synergies will be realized month-by-month over a set "
                "period, using an Ornstein-Uhlenbeck inspired realization curve."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "total_synergy_value": {
                    "type": "number",
                    "description": "Total expected synergy value in USD.",
                },
                "realization_months": {
                    "type": "integer",
                    "description": "Number of months to fully realize synergies (e.g., 24).",
                },
            },
            "required": ["total_synergy_value", "realization_months"],
        }

    async def execute(
        self, total_synergy_value: float = 0.0, realization_months: int = 24, **kwargs
    ) -> ToolResult:
        if realization_months <= 0:
            return ToolResult(
                success=False, data=None, error="realization_months must be > 0"
            )

        # We model this as an asymptotic catch-up (1 - e^(-kt)) where at t=realization_months, we are at 95%
        # 1 - e^(-k * months) = 0.95  => e^(-k * months) = 0.05 => -k * months = ln(0.05) => k = -ln(0.05)/months

        k = -math.log(0.05) / realization_months

        schedule = []
        cumulative_realized = 0.0

        for month in range(1, realization_months + 1):
            target_cumulative = total_synergy_value * (1 - math.exp(-k * month))
            incremental = target_cumulative - cumulative_realized
            cumulative_realized = target_cumulative

            # Simple way to capture the "last drop" at the end of the period
            if month == realization_months:
                incremental += total_synergy_value - cumulative_realized
                cumulative_realized = total_synergy_value

            schedule.append(
                {
                    "month": month,
                    "incremental_synergy": round(incremental, 2),
                    "cumulative_synergy": round(cumulative_realized, 2),
                    "percent_realized": (
                        round((cumulative_realized / total_synergy_value) * 100, 2)
                        if total_synergy_value
                        else 0.0
                    ),
                }
            )

        return ToolResult(
            success=True,
            data={
                "total_synergy_value": total_synergy_value,
                "realization_months": realization_months,
                "schedule": schedule,
            },
        )
