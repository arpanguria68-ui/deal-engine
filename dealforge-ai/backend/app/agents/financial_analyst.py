"""Financial Analyst Agent"""

from typing import Dict, Any, Optional, List
import json
import math
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput
from app.core.scoring.deal_scorer import DealScorer


class FinancialAnalystAgent(BaseAgent):
    """
    Agent for financial analysis and valuation

    Responsibilities:
    - Financial statement analysis
    - Valuation modeling (DCF, multiples)
    - Financial risk assessment
    - Return projections
    """

    name = "financial_analyst"
    description = "Analyzes financial performance and creates valuation models"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute financial analysis task

        Args:
            task: Analysis task description
            context: Deal context with financial data

        Returns:
            AgentOutput with financial analysis
        """
        start_time = datetime.now()
        self.logger.info("Starting financial analysis", task=task)

        # Retrieve relevant financial documents
        deal_id = context.get("deal_id") if context else None

        # Build context from memory
        memory_context = []
        if deal_id:
            memory_context = await self.retrieve_context(
                f"financial data revenue EBITDA cash flow {deal_id}", top_k=5
            )

        # Build analysis prompt
        prompt = self._build_analysis_prompt(task, context, memory_context)
        system_prompt = self._build_system_prompt()

        # Generate analysis with tools
        response = await self.generate_with_tools(prompt, system_prompt)

        # Parse and structure output
        try:
            analysis_data = self._parse_analysis_output(response["content"])

            # Add tool results if available
            if "tool_results" in response:
                analysis_data["calculations"] = response["tool_results"]

            # Calculate confidence
            confidence = self._calculate_confidence(analysis_data)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=analysis_data,
                reasoning=analysis_data.get("reasoning", ""),
                confidence=confidence,
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Failed to parse analysis", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Analysis failed: {str(e)}",
                confidence=0.0,
            )

    def _build_analysis_prompt(
        self, task: str, context: Optional[Dict], memory_context: list
    ) -> str:
        """Build the analysis prompt"""
        context_str = (
            json.dumps(context, indent=2) if context else "No additional context"
        )
        memory_str = (
            "\n".join([f"- {m['content'][:200]}..." for m in memory_context])
            if memory_context
            else "No retrieved documents"
        )

        return f"""Task: {task}

Context:
{context_str}

Relevant Documents:
{memory_str}

Provide a comprehensive financial analysis including:
1. Revenue analysis (growth trends, quality, concentration)
2. Profitability metrics (margins, trends)
3. Cash flow analysis
4. Balance sheet strength
5. Valuation estimate (DCF and multiples)
6. Key financial risks
7. Investment thesis from financial perspective

Respond with structured JSON:
{{
    "revenue_analysis": {{
        "annual_revenue": number,
        "growth_rate": number,
        "quality_assessment": string
    }},
    "profitability": {{
        "gross_margin": number,
        "ebitda_margin": number,
        "trend": string
    }},
    "cash_flow": {{
        "operating_cash_flow": number,
        "free_cash_flow": number,
        "burn_rate": number
    }},
    "valuation": {{
        "dcf_estimate": number,
        "multiple_estimate": number,
        "confidence_range": {{"low": number, "high": number}}
    }},
    "financial_risks": [string],
    "investment_thesis": string,
    "reasoning": string,
    "recommendation": "proceed" | "caution" | "reject"
}}"""

    def _build_system_prompt(self) -> str:
        """Build system prompt for financial analysis"""
        return f"""You are {self.name}, {self.description}.

You are an expert financial analyst with deep experience in:
- Financial modeling and valuation
- M&A transaction analysis
- Due diligence
- Investment thesis development

Guidelines:
- Use specific numbers and cite sources
- Show your calculation methodology
- Consider multiple valuation approaches
- Highlight both opportunities and risks
- Be conservative in projections
- Format all currency values consistently
"""

    def _parse_analysis_output(self, content: str) -> Dict[str, Any]:
        """Parse analysis output from LLM response"""
        from app.core.json_helpers import extract_and_parse_json

        return extract_and_parse_json(content)

    def _calculate_confidence(self, analysis_data: Dict) -> float:
        """Calculate confidence score for analysis"""
        confidence = 0.5

        # More data = higher confidence
        if analysis_data.get("revenue_analysis", {}).get("annual_revenue"):
            confidence += 0.15

        if analysis_data.get("valuation", {}).get("dcf_estimate"):
            confidence += 0.15

        if analysis_data.get("cash_flow", {}).get("operating_cash_flow"):
            confidence += 0.1

        # Reasoning present
        if analysis_data.get("reasoning") and len(analysis_data["reasoning"]) > 100:
            confidence += 0.1

        return min(1.0, confidence)

    async def run_valuation(
        self, financial_data: Dict[str, Any], method: str = "dcf"
    ) -> Dict[str, Any]:
        """
        Run specific valuation method

        Args:
            financial_data: Financial data for valuation
            method: Valuation method (dcf, multiples, combo)

        Returns:
            Valuation results
        """
        prompt = f"""Calculate {method.upper()} valuation for:

{json.dumps(financial_data, indent=2)}

Provide detailed calculation steps and final valuation."""

        response = await self.llm.generate(prompt, self._build_system_prompt())

        return {
            "method": method,
            "valuation": response["content"],
            "raw_data": financial_data,
        }

    # ===== Deterministic Financial Calculations =====

    @staticmethod
    def calculate_dcf(
        projected_fcf: List[float],
        wacc: float,
        terminal_growth: float = 0.025,
        mid_year_convention: bool = True,
    ) -> Dict[str, Any]:
        """
        Deterministic DCF calculation — 0% arithmetic error tolerance.
        Uses mid-year convention (stub period handling) by default per PRD.
        """
        if wacc <= terminal_growth:
            raise ValueError(
                f"WACC ({wacc}) must be > terminal growth ({terminal_growth})"
            )

        pv_cash_flows = []
        for i, fcf in enumerate(projected_fcf):
            period = i + 0.5 if mid_year_convention else i + 1
            pv = fcf / ((1 + wacc) ** period)
            pv_cash_flows.append({"year": i + 1, "fcf": fcf, "pv": round(pv, 2)})

        # Terminal Value (Gordon Growth Model)
        last_fcf = projected_fcf[-1]
        terminal_value = (last_fcf * (1 + terminal_growth)) / (wacc - terminal_growth)
        terminal_period = len(projected_fcf) + (0.5 if mid_year_convention else 1)
        pv_terminal = terminal_value / ((1 + wacc) ** terminal_period)

        enterprise_value = sum(pv["pv"] for pv in pv_cash_flows) + pv_terminal

        return {
            "method": "dcf",
            "mid_year_convention": mid_year_convention,
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "pv_cash_flows": pv_cash_flows,
            "terminal_value": round(terminal_value, 2),
            "pv_terminal_value": round(pv_terminal, 2),
            "enterprise_value": round(enterprise_value, 2),
        }

    @staticmethod
    def calculate_lbo_returns(
        entry_ev: float,
        exit_ev: float,
        equity_contribution_pct: float,
        holding_period_years: int = 5,
        total_debt_paydown: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Simplified LBO returns calculation.
        Returns IRR and MOIC for the equity sponsor.
        """
        initial_equity = entry_ev * equity_contribution_pct
        initial_debt = entry_ev - initial_equity
        remaining_debt = initial_debt - total_debt_paydown
        exit_equity = exit_ev - remaining_debt

        moic = exit_equity / initial_equity if initial_equity > 0 else 0
        irr = (moic ** (1 / holding_period_years)) - 1 if moic > 0 else -1.0

        return {
            "method": "lbo",
            "entry_ev": entry_ev,
            "exit_ev": exit_ev,
            "initial_equity": round(initial_equity, 2),
            "initial_debt": round(initial_debt, 2),
            "debt_paydown": total_debt_paydown,
            "exit_equity": round(exit_equity, 2),
            "moic": round(moic, 3),
            "irr": round(irr, 4),
        }

    @staticmethod
    def validate_unit_of_account(data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate consistent currency units across financial data.
        Flags entries where magnitude suggests unit mismatch (e.g., $M vs $K).
        """
        warnings = []
        revenue = data.get("revenue", 0)
        ebitda = data.get("ebitda", 0)
        fcf = data.get("free_cash_flow", 0)

        if revenue > 0 and ebitda > 0:
            margin = ebitda / revenue
            if margin > 1.0 or margin < -1.0:
                warnings.append(
                    f"EBITDA margin ({margin:.2%}) out of range — possible unit mismatch"
                )

        if revenue > 0 and fcf > 0:
            fcf_yield = fcf / revenue
            if fcf_yield > 1.0:
                warnings.append(
                    f"FCF yield ({fcf_yield:.2%}) exceeds revenue — possible unit mismatch"
                )

        return len(warnings) == 0, warnings


class ValuationAgent(BaseAgent):
    """Specialized agent for deal valuation"""

    name = "valuation_agent"
    description = "Specializes in company valuation using multiple methodologies"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Execute valuation task"""
        start_time = datetime.now()

        # Get comparable companies data
        market_data = context.get("market_data", {}) if context else {}
        financial_data = context.get("financial_data", {}) if context else {}

        # Run multiple valuation methods
        methods = ["dcf", "comparable_companies", "precedent_transactions"]
        valuations = {}

        for method in methods:
            valuations[method] = await self._run_valuation_method(
                method, financial_data, market_data
            )

        # Calculate weighted average
        weights = {
            "dcf": 0.4,
            "comparable_companies": 0.35,
            "precedent_transactions": 0.25,
        }
        weighted_value = sum(
            valuations[m]["value"] * weights[m]
            for m in methods
            if valuations[m].get("value")
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "valuations": valuations,
                "weighted_estimate": weighted_value,
                "valuation_range": {
                    "low": min(
                        v["value"] for v in valuations.values() if v.get("value")
                    ),
                    "high": max(
                        v["value"] for v in valuations.values() if v.get("value")
                    ),
                },
            },
            reasoning=f"Weighted valuation using {', '.join(methods)}",
            confidence=0.75,
            execution_time_ms=execution_time,
        )

    async def _run_valuation_method(
        self, method: str, financial_data: Dict, market_data: Dict
    ) -> Dict[str, Any]:
        """Run specific valuation method"""
        # This would integrate with actual calculation tools
        # For now, return structured placeholder

        if method == "dcf":
            # Use financial calculator tool
            result = await self.tools.execute(
                "financial_calculator",
                {
                    "calculation_type": "dcf",
                    "inputs": {
                        "cash_flows": financial_data.get(
                            "projected_cash_flows", [1000000, 1200000, 1500000]
                        ),
                        "discount_rate": financial_data.get("wacc", 0.12),
                        "terminal_growth": 0.025,
                    },
                },
            )

            if result.success:
                return {"method": method, "value": result.data.get("dcf_value", 0)}

        elif method == "comparable_companies":
            revenue = financial_data.get("revenue", 10000000)
            multiple = market_data.get("ev_revenue_median", 5)
            return {"method": method, "value": revenue * multiple}

        return {"method": method, "value": None}

    @staticmethod
    def calculate_comps_valuation(
        target_metric: float,
        peer_multiples: List[float],
        metric_name: str = "EV/EBITDA",
    ) -> Dict[str, Any]:
        """
        Comparable companies valuation using peer multiples.
        Returns median, mean, and range-based valuations.
        """
        if not peer_multiples:
            return {"method": "comps", "value": None, "error": "No peer data"}

        sorted_multiples = sorted(peer_multiples)
        n = len(sorted_multiples)
        median = (
            sorted_multiples[n // 2]
            if n % 2
            else (sorted_multiples[n // 2 - 1] + sorted_multiples[n // 2]) / 2
        )
        mean = sum(sorted_multiples) / n

        return {
            "method": "comparable_companies",
            "metric_name": metric_name,
            "target_metric": target_metric,
            "peer_multiples": sorted_multiples,
            "median_multiple": round(median, 2),
            "mean_multiple": round(mean, 2),
            "implied_value_median": round(target_metric * median, 2),
            "implied_value_mean": round(target_metric * mean, 2),
            "value_range": {
                "low": round(target_metric * sorted_multiples[0], 2),
                "high": round(target_metric * sorted_multiples[-1], 2),
            },
        }
