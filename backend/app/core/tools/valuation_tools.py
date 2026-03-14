"""
OFAS Valuation Tools — Comparable Companies, Football Field, Sensitivity Analysis

MCP Tools:
- fetch_comparable_companies: Identify peers and compute trading multiples
- generate_football_field: Populate template and generate valuation range chart
- run_sensitivity_analysis: 2D sensitivity tables (WACC × growth, multiple × margin)
- run_monte_carlo_irr: Stochastic simulation of M&A synergies and IRR using OU models
"""

import json
import math
import statistics
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from datetime import datetime
import structlog

from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger()


# ═══════════════════════════════════════════════
#  1. Fetch Comparable Companies
# ═══════════════════════════════════════════════


# Sector classification for peer identification
GICS_SECTOR_PEERS = {
    "technology": {
        "sub_sectors": [
            "software",
            "hardware",
            "semiconductors",
            "cloud",
            "saas",
            "cybersecurity",
        ],
        "default_multiples": {"ev_revenue": 6.0, "ev_ebitda": 18.0, "pe": 25.0},
    },
    "healthcare": {
        "sub_sectors": ["pharma", "biotech", "medtech", "healthcare_services"],
        "default_multiples": {"ev_revenue": 4.0, "ev_ebitda": 14.0, "pe": 20.0},
    },
    "financials": {
        "sub_sectors": ["banking", "insurance", "asset_management", "fintech"],
        "default_multiples": {"ev_revenue": 3.0, "ev_ebitda": 10.0, "pe": 12.0},
    },
    "consumer": {
        "sub_sectors": ["retail", "ecommerce", "consumer_goods", "food_beverage"],
        "default_multiples": {"ev_revenue": 2.0, "ev_ebitda": 12.0, "pe": 18.0},
    },
    "industrials": {
        "sub_sectors": ["manufacturing", "aerospace", "defense", "logistics"],
        "default_multiples": {"ev_revenue": 1.5, "ev_ebitda": 10.0, "pe": 15.0},
    },
    "energy": {
        "sub_sectors": ["oil_gas", "renewables", "utilities", "mining"],
        "default_multiples": {"ev_revenue": 1.0, "ev_ebitda": 6.0, "pe": 10.0},
    },
    "real_estate": {
        "sub_sectors": ["reit", "development", "proptech"],
        "default_multiples": {"ev_revenue": 5.0, "ev_ebitda": 15.0, "pe": 20.0},
    },
}


class FetchComparableCompaniesTool(BaseTool):
    """
    Identify peer companies and compute trading multiples for valuation.

    Can use Yahoo Finance data (if yfinance installed) or accept manually
    provided peer data. Computes quartile statistics for EV/Revenue,
    EV/EBITDA, and P/E multiples.
    """

    def __init__(self):
        super().__init__(
            name="fetch_comparable_companies",
            description=(
                "Identify peer companies, fetch their trading multiples (EV/Revenue, "
                "EV/EBITDA, P/E), and compute quartile statistics for comps valuation."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Target company ticker",
                },
                "sector": {
                    "type": "string",
                    "description": "Sector for peer identification",
                    "enum": list(GICS_SECTOR_PEERS.keys()),
                },
                "peer_tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional explicit list of peer tickers",
                },
                "target_metrics": {
                    "type": "object",
                    "description": (
                        "Target company financials: "
                        "{'revenue': ..., 'ebitda': ..., 'net_income': ..., 'shares_out': ...}"
                    ),
                },
            },
            "required": ["ticker", "sector"],
        }

    async def execute(
        self,
        ticker: str = "",
        sector: str = "technology",
        peer_tickers: Optional[List[str]] = None,
        target_metrics: Optional[Dict] = None,
        **kwargs,
    ) -> ToolResult:
        ticker = ticker.upper().strip()

        # Get sector info
        sector_info = GICS_SECTOR_PEERS.get(sector)
        if not sector_info:
            return ToolResult(
                success=False,
                data=None,
                error=f"Unknown sector: {sector}",
            )

        # Try fetching live data from Yahoo Finance
        peers_data = []
        if peer_tickers:
            peers_data = self._fetch_peer_multiples(peer_tickers)

        # If no live data available, use sector defaults
        if not peers_data:
            peers_data = self._generate_sector_defaults(sector_info, peer_tickers or [])

        # Compute quartile statistics
        stats = self._compute_quartile_stats(peers_data)

        # Compute implied valuations if target metrics provided
        implied = {}
        if target_metrics:
            revenue = target_metrics.get("revenue", 0)
            ebitda = target_metrics.get("ebitda", 0)
            net_income = target_metrics.get("net_income", 0)

            if revenue > 0 and stats.get("ev_revenue"):
                implied["ev_revenue"] = {
                    "25th": round(revenue * stats["ev_revenue"]["p25"], 2),
                    "median": round(revenue * stats["ev_revenue"]["median"], 2),
                    "75th": round(revenue * stats["ev_revenue"]["p75"], 2),
                }

            if ebitda > 0 and stats.get("ev_ebitda"):
                implied["ev_ebitda"] = {
                    "25th": round(ebitda * stats["ev_ebitda"]["p25"], 2),
                    "median": round(ebitda * stats["ev_ebitda"]["median"], 2),
                    "75th": round(ebitda * stats["ev_ebitda"]["p75"], 2),
                }

            if net_income > 0 and stats.get("pe"):
                implied["pe"] = {
                    "25th": round(net_income * stats["pe"]["p25"], 2),
                    "median": round(net_income * stats["pe"]["median"], 2),
                    "75th": round(net_income * stats["pe"]["p75"], 2),
                }

        return ToolResult(
            success=True,
            data={
                "ticker": ticker,
                "sector": sector,
                "peer_count": len(peers_data),
                "peers": peers_data,
                "quartile_stats": stats,
                "implied_valuations": implied,
            },
        )

    def _fetch_peer_multiples(self, tickers: List[str]) -> List[Dict]:
        """Fetch live peer multiples from Yahoo Finance"""
        try:
            import yfinance as yf
        except ImportError:
            return []

        peers = []
        for t in tickers:
            try:
                stock = yf.Ticker(t)
                info = stock.info or {}

                ev = info.get("enterpriseValue")
                revenue = info.get("totalRevenue")
                ebitda = info.get("ebitda")
                pe = info.get("trailingPE")
                market_cap = info.get("marketCap")

                peer = {
                    "ticker": t.upper(),
                    "name": info.get("shortName", t),
                    "market_cap": market_cap,
                    "enterprise_value": ev,
                }

                if ev and revenue and revenue > 0:
                    peer["ev_revenue"] = round(ev / revenue, 2)
                if ev and ebitda and ebitda > 0:
                    peer["ev_ebitda"] = round(ev / ebitda, 2)
                if pe and pe > 0:
                    peer["pe"] = round(pe, 2)

                peers.append(peer)

            except Exception as e:
                logger.warning("Failed to fetch peer data", ticker=t, error=str(e))

        return peers

    def _generate_sector_defaults(
        self, sector_info: Dict, tickers: List[str]
    ) -> List[Dict]:
        """Generate sector-default peer data when live data unavailable"""
        defaults = sector_info["default_multiples"]
        import random

        synthetic_peers = []
        # Use provided tickers or generate synthetic ones
        names = tickers if tickers else [f"Peer_{i+1}" for i in range(6)]

        for name in names:
            # Add some variance to create realistic distribution
            variance = random.uniform(0.7, 1.3)
            peer = {
                "ticker": name.upper(),
                "name": name,
                "source": "sector_default",
                "ev_revenue": round(defaults["ev_revenue"] * variance, 2),
                "ev_ebitda": round(defaults["ev_ebitda"] * variance, 2),
                "pe": round(defaults["pe"] * variance, 2),
            }
            synthetic_peers.append(peer)

        return synthetic_peers

    def _compute_quartile_stats(self, peers: List[Dict]) -> Dict[str, Dict]:
        """Compute quartile statistics for each multiple"""
        stats = {}

        for metric in ["ev_revenue", "ev_ebitda", "pe"]:
            values = [p[metric] for p in peers if metric in p and p[metric] is not None]
            if not values:
                continue

            sorted_vals = sorted(values)
            n = len(sorted_vals)

            stats[metric] = {
                "min": round(sorted_vals[0], 2),
                "p25": round(sorted_vals[max(0, n // 4 - 1)], 2),
                "median": round(statistics.median(sorted_vals), 2),
                "mean": round(statistics.mean(sorted_vals), 2),
                "p75": round(sorted_vals[min(n - 1, 3 * n // 4)], 2),
                "max": round(sorted_vals[-1], 2),
                "count": n,
            }

        return stats


# ═══════════════════════════════════════════════
#  2. Generate Football Field Chart
# ═══════════════════════════════════════════════


class GenerateFootballFieldTool(BaseTool):
    """
    Generate a football field valuation summary showing ranges from
    multiple valuation methodologies.

    Populates the Football-field-template.xlsx and also generates
    a standalone JSON summary for the Reporting agent.
    """

    def __init__(self):
        super().__init__(
            name="generate_football_field",
            description=(
                "Generate a football field chart showing valuation ranges from "
                "multiple methodologies (DCF, comps, precedent transactions, LBO). "
                "Returns structured data and optionally populates an Excel template."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Company ticker",
                },
                "valuation_ranges": {
                    "type": "object",
                    "description": (
                        "Valuation ranges by methodology. "
                        "Format: {'DCF': {'low': ..., 'mid': ..., 'high': ...}, "
                        "'EV/EBITDA Comps': {...}, ...}"
                    ),
                },
                "current_price": {
                    "type": "number",
                    "description": "Current share price (optional)",
                },
                "shares_outstanding": {
                    "type": "number",
                    "description": "Shares outstanding for per-share conversion",
                },
            },
            "required": ["ticker", "valuation_ranges"],
        }

    async def execute(
        self,
        ticker: str = "",
        valuation_ranges: Optional[Dict] = None,
        current_price: float = 0.0,
        shares_outstanding: float = 0.0,
        **kwargs,
    ) -> ToolResult:
        valuation_ranges = valuation_ranges or {}

        if not valuation_ranges:
            return ToolResult(
                success=False,
                data=None,
                error="At least one valuation methodology with low/mid/high is required",
            )

        # Calculate football field data
        methods = []
        all_lows = []
        all_highs = []

        for method_name, vals in valuation_ranges.items():
            low = vals.get("low", 0)
            mid = vals.get("mid", (low + vals.get("high", low)) / 2)
            high = vals.get("high", mid)

            # Per-share values if shares outstanding provided
            per_share = {}
            if shares_outstanding > 0:
                per_share = {
                    "low_per_share": round(low / shares_outstanding, 2),
                    "mid_per_share": round(mid / shares_outstanding, 2),
                    "high_per_share": round(high / shares_outstanding, 2),
                }

            method_data = {
                "name": method_name,
                "low": round(low, 2),
                "mid": round(mid, 2),
                "high": round(high, 2),
                "range_width": round(high - low, 2),
                **per_share,
            }
            methods.append(method_data)
            all_lows.append(low)
            all_highs.append(high)

        # Overall summary
        overall_low = min(all_lows)
        overall_high = max(all_highs)
        overall_mid = statistics.median([m["mid"] for m in methods])

        summary = {
            "ticker": ticker,
            "methodology_count": len(methods),
            "methods": methods,
            "composite_range": {
                "low": round(overall_low, 2),
                "mid": round(overall_mid, 2),
                "high": round(overall_high, 2),
            },
        }

        if current_price > 0 and shares_outstanding > 0:
            current_ev = current_price * shares_outstanding
            summary["current_price"] = current_price
            summary["current_market_cap"] = round(current_ev, 2)
            summary["upside_to_mid"] = round((overall_mid / current_ev - 1) * 100, 1)

        if shares_outstanding > 0:
            summary["composite_per_share"] = {
                "low": round(overall_low / shares_outstanding, 2),
                "mid": round(overall_mid / shares_outstanding, 2),
                "high": round(overall_high / shares_outstanding, 2),
            }

        # Try to populate the Excel template
        excel_result = self._populate_template(ticker, methods)
        if excel_result:
            summary["excel_path"] = excel_result

        return ToolResult(success=True, data=summary)

    def _populate_template(self, ticker: str, methods: List[Dict]) -> Optional[str]:
        """Attempt to populate Football-field-template.xlsx"""
        try:
            from app.core.tools.excel_model_engine import ExcelModelPopulateTool

            tool = ExcelModelPopulateTool()

            # Build cell mappings (template-specific — adjust for actual layout)
            cell_mappings = {}
            # Most football field templates have methods in rows, low/mid/high in columns
            # This is a best-effort mapping; exact cell addresses depend on the template
            sheet_name = "Sheet1"
            row_start = 5  # Typical starting row

            sheet_data = {}
            for i, method in enumerate(methods[:6]):  # Max 6 methodologies
                row = row_start + i
                sheet_data[f"A{row}"] = method["name"]
                sheet_data[f"B{row}"] = method["low"]
                sheet_data[f"C{row}"] = method["mid"]
                sheet_data[f"D{row}"] = method["high"]

            cell_mappings[sheet_name] = sheet_data

            result = tool.execute(
                template_id="football_field",
                ticker=ticker,
                cell_mappings=cell_mappings,
            )

            if result.success:
                return result.data.get("model_path")

        except Exception as e:
            logger.warning("Football field template population failed", error=str(e))

        return None


# ═══════════════════════════════════════════════
#  3. Sensitivity Analysis
# ═══════════════════════════════════════════════


class RunSensitivityAnalysisTool(BaseTool):
    """
    Run 2D sensitivity analysis on valuation parameters.

    Common analyses:
    - WACC × Terminal Growth Rate → Enterprise Value
    - EV/EBITDA Multiple × EBITDA Margin → Enterprise Value
    - Entry Multiple × Exit Multiple → IRR (for LBO)
    """

    def __init__(self):
        super().__init__(
            name="run_sensitivity_analysis",
            description=(
                "Run 2D sensitivity analysis on valuation parameters. "
                "Supports WACC×Growth, Multiple×EBITDA, Entry×Exit scenarios."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": [
                        "dcf_wacc_growth",
                        "comps_multiple_metric",
                        "lbo_entry_exit",
                    ],
                    "description": "Type of sensitivity analysis",
                },
                "base_inputs": {
                    "type": "object",
                    "description": "Base case inputs for the model",
                },
                "row_variable": {
                    "type": "object",
                    "description": (
                        "Row variable: {'name': 'wacc', 'values': [0.08, 0.10, 0.12, 0.14]}"
                    ),
                },
                "col_variable": {
                    "type": "object",
                    "description": (
                        "Column variable: {'name': 'terminal_growth', 'values': [0.01, 0.02, 0.03]}"
                    ),
                },
            },
            "required": [
                "analysis_type",
                "base_inputs",
                "row_variable",
                "col_variable",
            ],
        }

    async def execute(
        self,
        analysis_type: str = "dcf_wacc_growth",
        base_inputs: Optional[Dict] = None,
        row_variable: Optional[Dict] = None,
        col_variable: Optional[Dict] = None,
        **kwargs,
    ) -> ToolResult:
        base_inputs = base_inputs or {}
        row_variable = row_variable or {}
        col_variable = col_variable or {}

        row_values = row_variable.get("values", [])
        col_values = col_variable.get("values", [])
        row_name = row_variable.get("name", "row")
        col_name = col_variable.get("name", "col")

        if not row_values or not col_values:
            return ToolResult(
                success=False,
                data=None,
                error="Both row_variable and col_variable must have 'values' arrays",
            )

        # Build sensitivity table
        table = []
        for r_val in row_values:
            row_data = []
            for c_val in col_values:
                try:
                    if analysis_type == "dcf_wacc_growth":
                        value = self._calc_dcf(base_inputs, r_val, c_val)
                    elif analysis_type == "comps_multiple_metric":
                        value = self._calc_comps(base_inputs, r_val, c_val)
                    elif analysis_type == "lbo_entry_exit":
                        value = self._calc_lbo(base_inputs, r_val, c_val)
                    else:
                        value = None
                except Exception:
                    value = None
                row_data.append(round(value, 2) if value is not None else None)
            table.append(row_data)

        # Find the base case cell
        base_row_idx = self._find_closest_idx(row_values, base_inputs.get(row_name, 0))
        base_col_idx = self._find_closest_idx(col_values, base_inputs.get(col_name, 0))
        base_value = (
            table[base_row_idx][base_col_idx]
            if base_row_idx is not None and base_col_idx is not None
            else None
        )

        return ToolResult(
            success=True,
            data={
                "analysis_type": analysis_type,
                "row_variable": row_name,
                "col_variable": col_name,
                "row_values": row_values,
                "col_values": col_values,
                "table": table,
                "base_case": {
                    "row_idx": base_row_idx,
                    "col_idx": base_col_idx,
                    "value": base_value,
                },
                "range": {
                    "min": (
                        min(v for row in table for v in row if v is not None)
                        if any(v is not None for row in table for v in row)
                        else None
                    ),
                    "max": (
                        max(v for row in table for v in row if v is not None)
                        if any(v is not None for row in table for v in row)
                        else None
                    ),
                },
            },
        )

    def _calc_dcf(self, inputs: Dict, wacc: float, growth: float) -> Optional[float]:
        """DCF Enterprise Value for given WACC and terminal growth"""
        if wacc <= growth:
            return None

        fcfs = inputs.get("projected_fcf", [])
        if not fcfs:
            # Fallback: Generate if not provided
            base_fcf = inputs.get("fcf", 0)
            gr = inputs.get("growth_rate", 0.10)
            years = inputs.get("projection_years", 5)
            if base_fcf != 0:
                fcfs = [base_fcf * ((1 + gr) ** y) for y in range(1, years + 1)]
            else:
                return None

        pv = 0
        for i, fcf in enumerate(fcfs):
            pv += fcf / ((1 + wacc) ** (i + 0.5))  # Mid-year convention

        # Terminal value (Gordon Growth)
        tv = (fcfs[-1] * (1 + growth)) / (wacc - growth)
        pv_tv = tv / ((1 + wacc) ** (len(fcfs) + 0.5))

        return pv + pv_tv

    def _calc_comps(
        self, inputs: Dict, multiple: float, metric: float
    ) -> Optional[float]:
        """Implied EV = multiple × metric"""
        return multiple * metric

    def _calc_lbo(
        self, inputs: Dict, entry_multiple: float, exit_multiple: float
    ) -> Optional[float]:
        """LBO IRR for given entry and exit multiples"""
        ebitda_entry = inputs.get("ebitda_entry", 0)
        ebitda_exit = inputs.get("ebitda_exit", 0)
        equity_pct = inputs.get("equity_pct", 0.4)
        holding_years = inputs.get("holding_years", 5)
        debt_paydown = inputs.get("debt_paydown", 0)

        if ebitda_entry <= 0 or ebitda_exit <= 0:
            return None

        entry_ev = ebitda_entry * entry_multiple
        exit_ev = ebitda_exit * exit_multiple
        initial_equity = entry_ev * equity_pct
        initial_debt = entry_ev - initial_equity
        remaining_debt = initial_debt - debt_paydown
        exit_equity = exit_ev - remaining_debt

        if initial_equity <= 0 or exit_equity <= 0:
            return None

        moic = exit_equity / initial_equity
        irr = (moic ** (1 / holding_years)) - 1
        return irr * 100  # Return as percentage

    def _find_closest_idx(self, values: List[float], target: float) -> Optional[int]:
        """Find the index of the value closest to target"""
        if not values:
            return None
        return min(range(len(values)), key=lambda i: abs(values[i] - target))


# ═══════════════════════════════════════════════
#  4. Stochastic Monte Carlo IRR
# ═══════════════════════════════════════════════


class RunMonteCarloIRRTool(BaseTool):
    """
    Run Monte Carlo simulation for M&A IRR utilizing Stochastic Simulation Engine.
    Uses mean-reverting synergy fading (Ornstein-Uhlenbeck).
    """

    def __init__(self):
        super().__init__(
            name="run_monte_carlo_irr",
            description=(
                "Run a Monte Carlo IRR simulation using advanced stochastic models. "
                "Calculates probabilities of achieving target IRRs taking into account "
                "Ornstein-Uhlenbeck synergy fade execution risk."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "entry_ebitda": {
                    "type": "number",
                    "description": "Target's initial baseline EBITDA (annual)",
                },
                "price": {
                    "type": "number",
                    "description": "Upfront purchase price",
                },
                "syn_target": {
                    "type": "number",
                    "description": "Target synergies in Year 0",
                },
                "kappa": {
                    "type": "number",
                    "description": "Ornstein-Uhlenbeck speed of mean reversion (fade speed), default 0.5",
                    "default": 0.5,
                },
                "theta_pct": {
                    "type": "number",
                    "description": "Long-term sustainable synergies as % of target, default 0.5 (50%)",
                    "default": 0.5,
                },
                "sigma": {
                    "type": "number",
                    "description": "Execution risk volatility, default 2.0",
                    "default": 2.0,
                },
                "years": {
                    "type": "integer",
                    "description": "Projection years, default 5",
                    "default": 5,
                },
            },
            "required": ["entry_ebitda", "price", "syn_target"],
        }

    async def execute(
        self,
        entry_ebitda: float,
        price: float,
        syn_target: float,
        kappa: float = 0.5,
        theta_pct: float = 0.5,
        sigma: float = 2.0,
        years: int = 5,
        **kwargs,
    ) -> ToolResult:
        try:
            from app.core.tools.stochastic_engine import StochasticEngine

            engine = StochasticEngine(n_sim=5000)  # Slightly lower sim count for speed
            result = engine.run_irr_monte_carlo(
                entry_ebitda=entry_ebitda,
                price=price,
                syn_target=syn_target,
                kappa=kappa,
                theta_pct=theta_pct,
                sigma=sigma,
                T=years,
            )

            # Format the percent numbers for easy reading
            formatted_res = {
                "mean_irr": f"{result['mean_irr'] * 100:.2f}%",
                "median_irr": f"{result['median_irr'] * 100:.2f}%",
                "10th_percentile_irr": f"{result['p10_irr'] * 100:.2f}%",
                "90th_percentile_irr": f"{result['p90_irr'] * 100:.2f}%",
                "prob_above_15pct": f"{result['prob_above_15pct'] * 100:.1f}%",
                "note": "Simulation used Ornstein-Uhlenbeck mean-reverting synergy fade.",
            }

            return ToolResult(success=True, data=formatted_res)
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Monte Carlo simulation failed: {str(e)}",
            )
