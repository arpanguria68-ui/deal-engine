"""
Advanced Financial Modeler Agent

Computes sophisticated financial metrics including:
- Altman Z-Score (bankruptcy prediction)
- Value at Risk (VaR) - multiple methods
- DuPont Analysis (ROE decomposition)
- Intrinsic Growth Rate
- Cash Conversion Cycle
- Economic Value Added (EVA)
- Interest Coverage Ratios
- Leverage Analysis
- Profitability Index
- Sustainable Growth Rate
"""

from typing import Dict, Any, Optional, List
import json
import math
import io
import base64
from datetime import datetime
from dataclasses import dataclass

from app.agents.base import BaseAgent, AgentOutput
from app.core.json_helpers import extract_and_parse_json


class AdvancedFinancialModelerAgent(BaseAgent):
    """
    Advanced Financial Modeler — computes sophisticated financial metrics

    Capabilities:
    - Altman Z-Score for public/private/manufacturing companies
    - Value at Risk (VaR): Historical, Parametric, Monte Carlo
    - DuPont Analysis: ROE decomposition into components
    - Intrinsic Growth Rate (IGR) calculation
    - Cash Conversion Cycle analysis
    - Economic Value Added (EVA/MVA)
    - Comprehensive leverage and coverage metrics
    - Sustainable Growth Rate (SGR)
    """

    name = "advanced_financial_modeler"
    description: str = "Computes advanced financial metrics including Z-Score, VaR, DuPont analysis, and intrinsic growth rate"
    recommended_model: str = "Gemini 1.5 Pro (Precision Modeling)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute advanced financial modeling task

        Args:
            task: Analysis task description
            context: Deal context with financial data

        Returns:
            AgentOutput with advanced financial metrics
        """
        start_time = datetime.now()
        self.logger.info("Starting advanced financial modeling", task=task)

        context = context or {}
        deal_id = context.get("deal_id")
        ticker = context.get("ticker")

        # Guardrail: Ensure we have a ticker to avoid defaulting to AAPL
        if not ticker and "test" not in task.lower():
            self.logger.warning("No ticker provided for advanced modeling", task=task)
            # We'll still proceed but the prompt will now be explicit about the lack of ticker
            # in _build_analysis_prompt, or we can choose to fail.
            # Given this is an agent, let's make it fail or at least be very loud.
            # Returning failure if not a general "test" task.
            if not any(kw in task.lower() for kw in ["test", "demo", "general"]):
                return AgentOutput(
                    success=False,
                    data={},
                    reasoning=f"Advanced modeling failed: No ticker provided for target company. Context: {list(context.keys())}",
                    confidence=0.0,
                )

        # Retrieve relevant financial documents
        memory_context = []
        if deal_id:
            memory_context = await self.retrieve_context(
                f"financial statements balance sheet income cash flow {deal_id}",
                top_k=5,
            )

        # Get historical best practices
        from app.core.quality.agent_quality_store import AgentQualityStore

        quality_store = AgentQualityStore()
        await quality_store.initialize()
        best_practices = await quality_store.get_historical_best_practices(
            self.name, "advanced_financial_analysis"
        )

        # Build prompt and execute
        prompt = self._build_analysis_prompt(task, context, memory_context)
        system_prompt = self._build_system_prompt(best_practices)

        response = await self.generate_with_tools(prompt, system_prompt)

        # Parse and structure output
        try:
            analysis_data = self._parse_analysis_output(response.get("content", ""))

            # Run deterministic calculations if financial data available
            fin_data = context.get("financial_data", {})
            calc_results = {}
            if fin_data:
                calc_results = self._run_deterministic_calculations(fin_data, context)
                analysis_data["excel_model_base64"] = self._generate_excel_model(
                    fin_data
                )

            analysis_data["deterministic_calculations"] = calc_results

            # Add tool results if available
            if "tool_results" in response:
                analysis_data["tool_data"] = response["tool_results"]

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
            self.logger.error("Advanced financial modeling failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Advanced financial modeling failed: {str(e)}",
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

Provide comprehensive advanced financial analysis including:
1. Altman Z-Score calculation and bankruptcy risk assessment
2. Value at Risk (VaR) analysis using multiple methods
3. DuPont ROE decomposition analysis
4. Intrinsic Growth Rate (IGR) calculation
5. Cash Conversion Cycle analysis
6. Economic Value Added (EVA) assessment
7. Leverage and coverage metrics
8. Sustainable Growth Rate (SGR)
9. Profitability Index (PI)
10. Recommendations based on these metrics

Respond with structured JSON format with detailed calculations for each metric.
Include the formula used, inputs, and interpretation for each."""

    def _build_system_prompt(self, best_practices: List[str] = None) -> str:
        """Build system prompt for advanced financial modeling"""
        prompt = f"""You are {self.name}, {self.description}.

You are an expert in advanced financial analysis and quantitative risk modeling with deep experience in:
- Credit risk analysis and bankruptcy prediction
- Portfolio risk management and VaR modeling
- Corporate financial analysis and DuPont frameworks
- Value-based management (EVA, MVA)
- Growth analysis and capital allocation

CAPABILITIES:
- Altman Z-Score: Public, Private, and Manufacturing variants
- VaR Methods: Historical Simulation, Parametric (Variance-Covariance), Monte Carlo
- DuPont Analysis: 3-step and 5-step ROE decomposition
- IGR: Internal growth rate from retention ratio and ROA
- CCC: Cash conversion cycle (operating cycle - payables period)
- EVA: Economic Value Added = NOPAT - (WACC × Capital)
- SGR: Sustainable growth rate = ROE × Retention ratio

RULES:
- **CRITICAL: NEVER hallucinate financial data. Use tools to fetch real data.**
- If you need financial statements, use `fetch_financial_statements` or `financial_datasets`.
- Always show calculation methodology with formulas.
- Cite sources for all data used.
- Present results in structured JSON format with clear sections.
- Flag any assumptions explicitly."""

        if best_practices:
            prompt += "\n\nHistorical Best Practices:\n"
            for bp in best_practices:
                prompt += f"- {bp}\n"

        return prompt

    def _parse_analysis_output(self, content: str) -> Dict[str, Any]:
        """Parse analysis output from LLM response"""
        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content, "format": "narrative"}

    def _calculate_confidence(self, analysis_data: Dict) -> float:
        """Calculate confidence score for analysis"""
        confidence = 0.4

        # Deterministic calculations increase confidence
        calc_results = analysis_data.get("deterministic_calculations", {})

        if calc_results.get("altman_z_score"):
            confidence += 0.1

        if calc_results.get("var"):
            confidence += 0.1

        if calc_results.get("dupont_analysis"):
            confidence += 0.1

        if calc_results.get("intrinsic_growth_rate"):
            confidence += 0.1

        # Reasoning present
        if (
            analysis_data.get("reasoning")
            and len(analysis_data.get("reasoning", "")) > 100
        ):
            confidence += 0.1

        # Tool data available
        if analysis_data.get("tool_data"):
            confidence += 0.1

        return min(1.0, confidence)

    def _run_deterministic_calculations(
        self, fin_data: Dict, context: Dict
    ) -> Dict[str, Any]:
        """Run deterministic advanced financial calculations"""
        results = {}

        # Get company type for Z-Score
        company_type = fin_data.get(
            "company_type", "public"
        )  # public, private, manufacturing

        # Altman Z-Score
        if self._has_z_score_inputs(fin_data):
            results["altman_z_score"] = self._calculate_altman_z_score(
                fin_data, company_type
            )

        # Value at Risk
        if fin_data.get("returns") or fin_data.get("portfolio_value"):
            results["var"] = self._calculate_var(fin_data)

        # DuPont Analysis
        if self._has_dupont_inputs(fin_data):
            results["dupont_analysis"] = self._calculate_dupont(fin_data)

        # Intrinsic Growth Rate
        if fin_data.get("retention_ratio") and fin_data.get("roe"):
            results["intrinsic_growth_rate"] = self._calculate_igr(
                fin_data.get("retention_ratio"), fin_data.get("roe")
            )

        # Cash Conversion Cycle
        if self._has_ccc_inputs(fin_data):
            results["cash_conversion_cycle"] = self._calculate_ccc(fin_data)

        # EVA
        if self._has_eva_inputs(fin_data):
            results["economic_value_added"] = self._calculate_eva(fin_data)

        # Sustainable Growth Rate
        if fin_data.get("roe") and fin_data.get("retention_ratio"):
            results["sustainable_growth_rate"] = fin_data.get("roe") * fin_data.get(
                "retention_ratio"
            )

        # Leverage Ratios
        if self._has_leverage_inputs(fin_data):
            results["leverage_analysis"] = self._calculate_leverage_ratios(fin_data)

        # Coverage Ratios
        if self._has_coverage_inputs(fin_data):
            results["coverage_ratios"] = self._calculate_coverage_ratios(fin_data)

        return results

    def _has_z_score_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for Z-Score"""
        required = [
            "working_capital",
            "retained_earnings",
            "ebit",
            "market_value_equity",
            "total_assets",
            "total_liabilities",
            "sales",
        ]
        return all(data.get(k) is not None for k in required)

    def _has_dupont_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for DuPont"""
        return all(
            data.get(k) is not None for k in ["net_income", "sales", "assets", "equity"]
        )

    def _has_ccc_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for CCC"""
        return any(
            data.get(k) for k in ["inventory_days", "receivables_days", "payables_days"]
        )

    def _has_eva_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for EVA"""
        return all(data.get(k) for k in ["nopat", "capital", "wacc"])

    def _has_leverage_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for leverage ratios"""
        return any(
            data.get(k)
            for k in ["total_debt", "total_assets", "equity", "total_liabilities"]
        )

    def _has_coverage_inputs(self, data: Dict) -> bool:
        """Check if we have inputs for coverage ratios"""
        return any(data.get(k) for k in ["ebit", "interest_expense", "fixed_charges"])

    # ═══════════════════════════════════════════════
    #  Altman Z-Score Calculations
    # ═══════════════════════════════════════════════

    def _calculate_altman_z_score(
        self, data: Dict, company_type: str = "public"
    ) -> Dict:
        """
        Calculate Altman Z-Score

        For Public Companies:
        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5

        For Private Companies:
        Z = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5

        For Manufacturing:
        Z = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5

        Where:
        X1 = Working Capital / Total Assets
        X2 = Retained Earnings / Total Assets
        X3 = EBIT / Total Assets
        X4 = Market Value of Equity / Total Liabilities
        X5 = Sales / Total Assets
        """
        wc = data.get("working_capital", 0)
        re = data.get("retained_earnings", 0)
        ebit = data.get("ebit", 0)
        mv = data.get("market_value_equity", 0)
        sales = data.get("sales", 0)
        assets = data.get("total_assets", 1)
        liabilities = data.get("total_liabilities", 1)

        # Avoid division by zero
        if assets == 0:
            return {"error": "Total assets cannot be zero"}
        if liabilities == 0:
            liabilities = 1  # Avoid division by zero

        x1 = wc / assets  # Working Capital / Total Assets
        x2 = re / assets  # Retained Earnings / Total Assets
        x3 = ebit / assets  # EBIT / Total Assets
        x4 = mv / liabilities  # Market Value Equity / Total Liabilities
        x5 = sales / assets  # Sales / Total Assets

        if company_type == "public":
            z_score = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        elif company_type == "private":
            z_score = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
        else:  # manufacturing
            z_score = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5

        # Interpretation
        if z_score > 2.99:
            interpretation = "Safe zone - Low probability of bankruptcy"
            risk_level = "low"
        elif z_score > 1.81:
            interpretation = "Grey zone - Uncertain"
            risk_level = "medium"
        else:
            interpretation = "Distress zone - High probability of bankruptcy"
            risk_level = "high"

        return {
            "z_score": round(z_score, 2),
            "company_type": company_type,
            "components": {
                "x1_working_capital_ratio": round(x1, 4),
                "x2_retained_earnings_ratio": round(x2, 4),
                "x3_ebit_ratio": round(x3, 4),
                "x4_equity_liability_ratio": round(x4, 4),
                "x5_sales_asset_ratio": round(x5, 4),
            },
            "interpretation": interpretation,
            "risk_level": risk_level,
            "formula": (
                "Public: Z = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5"
                if company_type == "public"
                else "Private/Manufacturing: Z = 0.717X1 + 0.847X2 + 3.107X3 + 0.420X4 + 0.998X5"
            ),
        }

    # ═══════════════════════════════════════════════
    #  Value at Risk (VaR) Calculations
    # ═══════════════════════════════════════════════

    def _calculate_var(self, data: Dict) -> Dict:
        """
        Calculate Value at Risk using multiple methods

        Methods:
        1. Historical Simulation
        2. Parametric (Variance-Covariance)
        3. Monte Carlo Simulation
        """
        results = {}

        # Historical Simulation VaR
        returns = data.get("returns", [])
        if len(returns) > 30:
            results["historical_var"] = self._historical_var(
                returns, data.get("confidence_level", 0.95)
            )

        # Parametric VaR
        if data.get("mean_return") and data.get("volatility"):
            results["parametric_var"] = self._parametric_var(
                data.get("mean_return"),
                data.get("volatility"),
                data.get("portfolio_value", 1000000),
                data.get("confidence_level", 0.95),
                data.get("time_horizon", 1),
            )

        # Monte Carlo VaR
        if data.get("volatility") and data.get("portfolio_value"):
            results["monte_carlo_var"] = self._monte_carlo_var(
                data.get("portfolio_value", 1000000),
                data.get("volatility"),
                data.get("mean_return", 0.0),
                data.get("confidence_level", 0.95),
                data.get("time_horizon", 1),
                data.get("simulations", 10000),
            )

        return results

    def _historical_var(self, returns: List[float], confidence: float = 0.95) -> Dict:
        """Historical Simulation VaR"""
        sorted_returns = sorted(returns)
        index = int((1 - confidence) * len(sorted_returns))
        var_percentile = sorted_returns[max(0, index)]

        return {
            "method": "Historical Simulation",
            "var_percentile": round(var_percentile, 4),
            "confidence_level": confidence,
            "interpretation": f"With {confidence*100}% confidence, losses will not exceed {abs(var_percentile)*100:.2f}% in the given period",
        }

    def _parametric_var(
        self,
        mean: float,
        vol: float,
        value: float,
        confidence: float = 0.95,
        horizon: int = 1,
    ) -> Dict:
        """Parametric (Variance-Covariance) VaR using normal distribution"""
        import numpy as np

        # Z-score for confidence level
        z_scores = {0.90: 1.28, 0.95: 1.645, 0.99: 2.33}
        z = z_scores.get(confidence, 1.645)

        # Scale volatility by square root of time
        scaled_vol = vol * math.sqrt(horizon)

        var_absolute = value * (mean * horizon - z * scaled_vol)

        return {
            "method": "Parametric (Variance-Covariance)",
            "var_absolute": round(abs(var_absolute), 2),
            "var_percentage": round(abs(var_absolute / value), 4),
            "confidence_level": confidence,
            "time_horizon_days": horizon,
            "z_score": z,
            "interpretation": f"With {confidence*100}% confidence, maximum expected loss is ${abs(var_absolute):,.2f} over {horizon} day(s)",
        }

    def _monte_carlo_var(
        self,
        value: float,
        vol: float,
        mean: float,
        confidence: float = 0.95,
        horizon: int = 1,
        simulations: int = 10000,
    ) -> Dict:
        """Monte Carlo Simulation VaR"""
        import numpy as np

        np.random.seed(42)  # For reproducibility

        # Generate random returns
        dt = horizon / 252  # Daily time step
        random_returns = np.random.normal(mean * dt, vol * np.sqrt(dt), simulations)

        # Calculate portfolio values
        portfolio_values = value * (1 + random_returns)

        # Get VaR percentile
        var_percentile = np.percentile(portfolio_values, (1 - confidence) * 100)
        var_absolute = value - var_percentile

        return {
            "method": "Monte Carlo Simulation",
            "var_absolute": round(var_absolute, 2),
            "var_percentage": round(var_absolute / value, 4),
            "confidence_level": confidence,
            "simulations": simulations,
            "time_horizon_days": horizon,
            "interpretation": f"Monte Carlo simulation with {simulations} runs shows {confidence*100}% VaR of ${var_absolute:,.2f}",
        }

    # ═══════════════════════════════════════════════
    #  DuPont Analysis
    # ═══════════════════════════════════════════════

    def _calculate_dupont(self, data: Dict) -> Dict:
        """
        DuPont Analysis - ROE Decomposition

        3-Step DuPont:
        ROE = Net Margin × Asset Turnover × Equity Multiplier

        5-Step DuPont:
        ROE = Tax Burden × Interest Burden × Operating Margin × Asset Turnover × Equity Multiplier
        """
        net_income = data.get("net_income", 0)
        sales = data.get("sales", 1)
        assets = data.get("assets", 1)
        equity = data.get("equity", 1)
        ebit = data.get("ebit", 0)
        interest = data.get("interest_expense", 0)
        tax = data.get("tax_expense", 0)

        # Avoid division by zero
        if sales == 0:
            sales = 1
        if assets == 0:
            assets = 1
        if equity == 0:
            equity = 1

        # 3-Step DuPont
        net_margin = net_income / sales
        asset_turnover = sales / assets
        equity_multiplier = assets / equity

        roe_3step = net_margin * asset_turnover * equity_multiplier

        # 5-Step DuPont (if we have EBIT and interest)
        if ebit > 0 and interest > 0:
            tax_burden = (
                net_income / (ebit - interest + tax)
                if (ebit - interest + tax) > 0
                else 0
            )
            interest_burden = (ebit - interest) / ebit if ebit > 0 else 0
            operating_margin = ebit / sales
            asset_turnover_5 = sales / assets
            equity_multiplier_5 = assets / equity

            roe_5step = (
                tax_burden
                * interest_burden
                * operating_margin
                * asset_turnover_5
                * equity_multiplier_5
            )
        else:
            tax_burden = None
            interest_burden = None
            operating_margin = None
            roe_5step = None

        return {
            "roe_3step": round(roe_3step, 4) if roe_3step else None,
            "components_3step": {
                "net_margin": round(net_margin, 4),
                "asset_turnover": round(asset_turnover, 4),
                "equity_multiplier": round(equity_multiplier, 4),
            },
            "roe_5step": round(roe_5step, 4) if roe_5step else None,
            "components_5step": {
                "tax_burden": round(tax_burden, 4) if tax_burden else None,
                "interest_burden": (
                    round(interest_burden, 4) if interest_burden else None
                ),
                "operating_margin": (
                    round(operating_margin, 4) if operating_margin else None
                ),
                "asset_turnover": (
                    round(asset_turnover_5, 4) if asset_turnover_5 else None
                ),
                "equity_multiplier": (
                    round(equity_multiplier_5, 4) if equity_multiplier_5 else None
                ),
            },
            "interpretation": self._interpret_dupont(
                net_margin, asset_turnover, equity_multiplier
            ),
        }

    def _interpret_dupont(
        self, margin: float, turnover: float, multiplier: float
    ) -> str:
        """Interpret DuPont results"""
        interpretations = []

        # Net margin analysis
        if margin > 0.15:
            interpretations.append("High profitability (strong net margin)")
        elif margin > 0.05:
            interpretations.append("Moderate profitability")
        else:
            interpretations.append("Low profitability - focus on cost control")

        # Asset turnover analysis
        if turnover > 1.5:
            interpretations.append("Strong asset utilization")
        elif turnover > 0.5:
            interpretations.append("Moderate asset efficiency")
        else:
            interpretations.append("Low asset turnover - consider improving efficiency")

        # Equity multiplier (leverage)
        if multiplier > 2.5:
            interpretations.append("High financial leverage")
        elif multiplier > 1.5:
            interpretations.append("Moderate leverage")
        else:
            interpretations.append("Conservative capital structure")

        return "; ".join(interpretations)

    # ═══════════════════════════════════════════════
    #  Intrinsic Growth Rate (IGR)
    # ═══════════════════════════════════════════════

    def _calculate_igr(self, retention_ratio: float, roe: float) -> Dict:
        """
        Intrinsic Growth Rate (IGR)

        IGR = (ROE × Retention Ratio) / (1 - ROE × Retention Ratio)

        Alternative (simpler):
        IGR = ROE × Retention Ratio
        """
        # Simple IGR
        igr_simple = roe * retention_ratio

        # Sustainable IGR (with financing assumptions)
        if roe * retention_ratio < 1:
            igr_sustainable = (roe * retention_ratio) / (1 - roe * retention_ratio)
        else:
            igr_sustainable = None  # Not sustainable

        return {
            "intrinsic_growth_rate_simple": round(igr_simple, 4),
            "intrinsic_growth_rate_sustainable": (
                round(igr_sustainable, 4) if igr_sustainable else None
            ),
            "retention_ratio": retention_ratio,
            "roe": roe,
            "interpretation": f"Company can grow at {igr_simple*100:.1f}% annually without external financing",
        }

    # ═══════════════════════════════════════════════
    #  Cash Conversion Cycle (CCC)
    # ═══════════════════════════════════════════════

    def _calculate_ccc(self, data: Dict) -> Dict:
        """
        Cash Conversion Cycle

        CCC = Days Inventory Outstanding + Days Sales Outstanding - Days Payables Outstanding
        """
        dio = data.get("inventory_days", 0)  # Days Inventory Outstanding
        dso = data.get("receivables_days", 0)  # Days Sales Outstanding
        dpo = data.get("payables_days", 0)  # Days Payables Outstanding

        ccc = dio + dso - dpo

        return {
            "cash_conversion_cycle_days": round(ccc, 1),
            "components": {
                "days_inventory_outstanding": dio,
                "days_sales_outstanding": dso,
                "days_payables_outstanding": dpo,
            },
            "interpretation": self._interpret_ccc(ccc),
        }

    def _interpret_ccc(self, ccc: float) -> str:
        """Interpret Cash Conversion Cycle"""
        if ccc < 0:
            return f"Negative CCC ({ccc:.0f} days) - Company receives cash before paying suppliers (ideal)"
        elif ccc < 30:
            return f"Low CCC ({ccc:.0f} days) - Efficient working capital management"
        elif ccc < 60:
            return f"Moderate CCC ({ccc:.0f} days) - Standard for most industries"
        else:
            return f"High CCC ({ccc:.0f} days) - Consider improving collections and inventory management"

    # ═══════════════════════════════════════════════
    #  Economic Value Added (EVA)
    # ═══════════════════════════════════════════════

    def _calculate_eva(self, data: Dict) -> Dict:
        """
        Economic Value Added (EVA)

        EVA = NOPAT - (WACC × Capital)

        Where:
        - NOPAT = Net Operating Profit After Tax
        - WACC = Weighted Average Cost of Capital
        - Capital = Total Capital (Debt + Equity)
        """
        nopat = data.get("nopat", 0)
        capital = data.get("capital", data.get("total_assets", 0))
        wacc = data.get("wacc", 0.10)

        capital_charge = capital * wacc
        eva = nopat - capital_charge

        # Market Value Added (MVA)
        market_value = data.get("market_value", 0)
        mva = market_value - capital if market_value else None

        return {
            "economic_value_added": round(eva, 2),
            "nopat": round(nopat, 2),
            "capital_charge": round(capital_charge, 2),
            "capital": round(capital, 2),
            "wacc": wacc,
            "market_value_added": round(mva, 2) if mva else None,
            "interpretation": (
                "Positive EVA - Creating value for shareholders"
                if eva > 0
                else "Negative EVA - Destroying shareholder value"
            ),
        }

    # ═══════════════════════════════════════════════
    #  Leverage & Coverage Ratios
    # ═══════════════════════════════════════════════

    def _calculate_leverage_ratios(self, data: Dict) -> Dict:
        """Calculate leverage ratios"""
        debt = data.get("total_debt", 0)
        equity = data.get("equity", 1)
        assets = data.get("total_assets", 1)
        liabilities = data.get("total_liabilities", 0)

        if equity == 0:
            equity = 1
        if assets == 0:
            assets = 1

        debt_to_equity = debt / equity if equity else 0
        debt_to_assets = debt / assets if assets else 0
        equity_ratio = equity / assets if assets else 0

        return {
            "debt_to_equity": round(debt_to_equity, 2),
            "debt_to_assets": round(debt_to_assets, 2),
            "equity_ratio": round(equity_ratio, 2),
            "debt_to_capital": round(
                debt / (debt + equity) if (debt + equity) > 0 else 0, 2
            ),
            "interpretation": self._interpret_leverage(debt_to_equity, debt_to_assets),
        }

    def _calculate_coverage_ratios(self, data: Dict) -> Dict:
        """Calculate coverage ratios"""
        ebit = data.get("ebit", 0)
        interest = data.get("interest_expense", 1)
        fixed_charges = data.get("fixed_charges", 0)

        if interest == 0:
            interest = 1  # Avoid division by zero

        interest_coverage = ebit / interest if interest > 0 else None
        fixed_charge_coverage = (
            (ebit + fixed_charges) / (interest + fixed_charges)
            if (interest + fixed_charges) > 0
            else None
        )

        return {
            "interest_coverage_ratio": (
                round(interest_coverage, 2) if interest_coverage else None
            ),
            "fixed_charge_coverage": (
                round(fixed_charge_coverage, 2) if fixed_charge_coverage else None
            ),
            "interpretation": self._interpret_coverage(interest_coverage),
        }

    def _interpret_leverage(self, dte: float, dta: float) -> str:
        """Interpret leverage ratios"""
        if dte > 2.0:
            return "High leverage - elevated financial risk"
        elif dte > 1.0:
            return "Moderate leverage - typical for leveraged buyouts"
        else:
            return "Conservative leverage - low financial risk"

    def _interpret_coverage(self, coverage: float) -> str:
        """Interpret coverage ratios"""
        if coverage is None:
            return "Unable to calculate - missing EBIT or interest data"
        elif coverage < 1:
            return f"Coverage ratio {coverage:.1f}x - danger of default"
        elif coverage < 2:
            return f"Coverage ratio {coverage:.1f}x - concerning, may strain finances"
        elif coverage < 4:
            return f"Coverage ratio {coverage:.1f}x - acceptable for most lenders"
        else:
            return f"Coverage ratio {coverage:.1f}x - strong debt servicing ability"

    def _generate_excel_model(self, fin_data: Dict) -> str:
        """Generate an Excel workbook with embedded formulas for DCF/LBO"""
        try:
            import xlsxwriter
        except ImportError:
            return ""

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        # DCF Model Sheet
        dcf_sheet = workbook.add_worksheet("DCF Model")

        # Formats
        header_format = workbook.add_format(
            {"bold": True, "bottom": 1, "bg_color": "#D9D9D9"}
        )
        currency_format = workbook.add_format({"num_format": "$#,##0.00"})
        pct_format = workbook.add_format({"num_format": "0.0%"})

        dcf_sheet.write(0, 0, "DCF Model", header_format)
        dcf_sheet.write(2, 0, "Year")
        dcf_sheet.write(3, 0, "Free Cash Flow")
        dcf_sheet.write(4, 0, "Discount Factor")
        dcf_sheet.write(5, 0, "PV of FCF")

        fcf = fin_data.get("projected_fcf", [100.0, 110.0, 121.0, 133.0, 146.0])
        wacc = fin_data.get("wacc", 0.10)

        # Write WACC assumption
        dcf_sheet.write(0, 2, "WACC Input:", header_format)
        dcf_sheet.write_number(0, 3, wacc, pct_format)

        for i, cf in enumerate(fcf):
            col = i + 1
            col_letter = chr(65 + col)
            dcf_sheet.write(2, col, f"Year {i+1}", header_format)
            dcf_sheet.write_number(3, col, float(cf), currency_format)

            # Discount Factor Formula (Mid-Year): =1/((1+$D$1)^(Year-0.5))
            dcf_sheet.write_formula(4, col, f"=1/((1+$D$1)^({i+0.5}))", pct_format)

            # PV Formula: FCF * Discount Factor
            dcf_sheet.write_formula(
                5, col, f"={col_letter}4*{col_letter}5", currency_format
            )

        # Enterprise Value Sum
        dcf_sheet.write(7, 0, "Sum of PV of FCFs", header_format)
        end_col = chr(65 + len(fcf))
        dcf_sheet.write_formula(7, 1, f"=SUM(B6:{end_col}6)", currency_format)

        # LBO Model Sheet
        lbo_sheet = workbook.add_worksheet("LBO Model")
        lbo_sheet.write(0, 0, "LBO Returns Analysis", header_format)
        lbo_sheet.write(2, 0, "Entry Enterprise Value")
        lbo_sheet.write(3, 0, "Exit Enterprise Value")
        lbo_sheet.write(4, 0, "Equity Percentage")
        lbo_sheet.write(5, 0, "Equity Invested")
        lbo_sheet.write(6, 0, "Exit Equity Value")
        lbo_sheet.write(7, 0, "MOIC")
        lbo_sheet.write(8, 0, "IRR (5-Year Hold)")

        entry_ev = fin_data.get("entry_ev", 1000)
        exit_ev = fin_data.get("exit_ev", 2000)
        eq_pct = fin_data.get("equity_pct", 0.40)

        lbo_sheet.write_number(2, 1, entry_ev, currency_format)
        lbo_sheet.write_number(3, 1, exit_ev, currency_format)
        lbo_sheet.write_number(4, 1, eq_pct, pct_format)

        lbo_sheet.write_formula(5, 1, "=B3*B5", currency_format)  # Entry EV * Eq%
        lbo_sheet.write_formula(
            6, 1, "=B4-(B3*(1-B5))", currency_format
        )  # Exit EV - Debt
        lbo_sheet.write_formula(
            7, 1, "=B7/B6", workbook.add_format({"num_format": '0.0"x"'})
        )  # Exit / Entry
        lbo_sheet.write_formula(8, 1, "=(B8^(1/5))-1", pct_format)

        workbook.close()
        output.seek(0)
        return base64.b64encode(output.read()).decode("utf-8")


# ═══════════════════════════════════════════════
#  Module Exports
# ═══════════════════════════════════════════════

__all__ = ["AdvancedFinancialModelerAgent"]
