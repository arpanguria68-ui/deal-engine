"""
Treasury, FP&A, and Tax Compliance Agents

CFO Advisory suite for cash positioning, forecasting, and tax analysis.
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class TreasuryCashAgent(BaseAgent):
    """Treasury Cash Positioning Agent — liquidity forecasting and cash management."""

    name = "treasury_agent"
    description = "Cash positioning, liquidity forecasting, currency exposure analysis"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are a Senior Treasury Analyst.
Analyze cash positions, predict cash flows, and recommend liquidity actions.

ANALYSIS AREAS:
1. Current cash position across entities/currencies
2. Near-term inflow/outflow projections (13-week)
3. Currency exposure and hedging needs
4. Intercompany transfer opportunities
5. Working capital optimization

Always present a clear 13-week cash forecast with confidence bands."""

            prompt = (
                f"TASK: {task}\n\nCONTEXT: {json.dumps(context, default=str)[:2000]}"
            )

            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")

            # Run deterministic cash calculations if data available
            calc = {}
            if context.get("cash_data"):
                calc = self._forecast_cash(context["cash_data"])

            analysis = self._parse_output(content)
            analysis["calculations"] = calc

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=analysis,
                reasoning="Completed treasury analysis with cash flow projections.",
                confidence=0.80,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    @staticmethod
    def _forecast_cash(data: Dict) -> Dict:
        """Simple 13-week cash flow projection."""
        opening = data.get("opening_balance", 0)
        weekly_inflow = data.get("avg_weekly_inflow", 0)
        weekly_outflow = data.get("avg_weekly_outflow", 0)

        forecast = []
        balance = opening
        for week in range(1, 14):
            balance += weekly_inflow - weekly_outflow
            forecast.append(
                {
                    "week": week,
                    "inflow": weekly_inflow,
                    "outflow": weekly_outflow,
                    "closing_balance": round(balance, 2),
                }
            )
        return {
            "forecast": forecast,
            "min_balance": min(f["closing_balance"] for f in forecast),
        }

    def _parse_output(self, content: str) -> Dict:
        from app.core.json_helpers import extract_and_parse_json

        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content}


class FPAForecastingAgent(BaseAgent):
    """FP&A Forecasting Agent — scenario-based financial planning."""

    name = "fpa_forecasting_agent"
    description = (
        "Financial planning & analysis with scenario modeling and variance analysis"
    )

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are a Head of FP&A at a Fortune 500 company.

CAPABILITIES:
1. Revenue forecasting with driver-based models
2. Scenario analysis (base/bull/bear)
3. Variance analysis (actual vs budget vs forecast)
4. Rolling forecast updates
5. Board-ready commentary

Always present 3 scenarios with probability weights."""

            prompt = (
                f"TASK: {task}\n\nCONTEXT: {json.dumps(context, default=str)[:2000]}"
            )
            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=self._parse_output(content),
                reasoning="Generated FP&A forecast with scenario analysis.",
                confidence=0.80,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    def _parse_output(self, content: str) -> Dict:
        from app.core.json_helpers import extract_and_parse_json

        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content}


class TaxComplianceAgent(BaseAgent):
    """Tax & Regulatory Compliance Agent."""

    name = "tax_compliance_agent"
    description = (
        "Tax provision calculations, regulatory compliance, transfer pricing analysis"
    )

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            system_prompt = """You are a Senior Tax Director at a Big 4 firm.

ANALYSIS AREAS:
1. Tax provision estimation (ASC 740)
2. Transfer pricing risk assessment
3. M&A tax due diligence (entity structure, NOLs, 382 limitations)
4. VAT/GST compliance verification
5. Regulatory change impact analysis

Flag any material tax risks or planning opportunities."""

            prompt = (
                f"TASK: {task}\n\nCONTEXT: {json.dumps(context, default=str)[:2000]}"
            )
            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=self._parse_output(content),
                reasoning="Completed tax compliance analysis.",
                confidence=0.78,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    def _parse_output(self, content: str) -> Dict:
        from app.core.json_helpers import extract_and_parse_json

        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content}
