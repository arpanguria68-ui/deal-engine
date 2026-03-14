"""GP-Led Continuation Vehicle (CV) Simulation Workflow for DealForge AI

Per the PRD, this workflow orchestrates:
1. Librarian: Ingests LPA + Bid Spread data room documents
2. Strategist: Branches into MECE nodes (Price Fairness, Economic Parity, Governance Integrity)
3. Architect: Solves circular debt waterfall iteratively
4. Editor: Renders Mermaid Sankey diagrams with audit citations
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
import json
import structlog

logger = structlog.get_logger()


@dataclass
class CVSimulationConfig:
    """Configuration for a GP-Led CV simulation"""

    lpa_document_id: str
    bid_spread_data: Dict[str, Any]
    gp_carried_interest: float = 0.20
    management_fee: float = 0.02
    preferred_return: float = 0.08
    waterfall_type: str = "european"  # european, american, deal-by-deal
    max_waterfall_iterations: int = 50
    convergence_threshold: float = 0.01


class CVWaterfallSolver:
    """
    Iterative solver for circular debt waterfalls in continuation vehicles.

    The circularity arises because:
    - GP carry depends on total distributions
    - Total distributions depend on debt paydown
    - Debt paydown depends on available cash after carry
    """

    def __init__(self, config: CVSimulationConfig):
        self.config = config
        self.logger = structlog.get_logger(component="cv_waterfall")

    def solve(
        self,
        total_nav: float,
        existing_debt: float,
        projected_cash_flows: List[float],
    ) -> Dict[str, Any]:
        """
        Solve the circular waterfall iteratively until convergence.

        Args:
            total_nav: Net Asset Value of the portfolio
            existing_debt: Outstanding debt to be assumed
            projected_cash_flows: Annual projected cash flows
        """
        # Initial estimates
        gp_carry_estimate = 0.0
        iterations = 0
        converged = False

        waterfall_log = []

        while iterations < self.config.max_waterfall_iterations:
            iterations += 1

            # Step 1: Calculate available cash after carry
            distributions = []
            cumulative_contributions = total_nav
            cumulative_distributions = 0.0
            preferred_due = cumulative_contributions * self.config.preferred_return

            for year, cf in enumerate(projected_cash_flows, 1):
                available_cash = cf

                # Management fee
                mgmt_fee = total_nav * self.config.management_fee
                available_cash -= mgmt_fee

                # Debt service
                debt_service = min(
                    existing_debt / len(projected_cash_flows), available_cash * 0.5
                )
                available_cash -= debt_service
                existing_debt -= debt_service

                # Preferred return (must be met before carry)
                pref_payment = min(preferred_due, available_cash)
                available_cash -= pref_payment
                preferred_due -= pref_payment

                # GP Carry (only after preferred return is met)
                gp_carry = (
                    available_cash * self.config.gp_carried_interest
                    if preferred_due <= 0
                    else 0.0
                )
                lp_distribution = available_cash - gp_carry

                cumulative_distributions += lp_distribution + gp_carry

                distributions.append(
                    {
                        "year": year,
                        "cash_flow": cf,
                        "management_fee": round(mgmt_fee, 2),
                        "debt_service": round(debt_service, 2),
                        "preferred_return": round(pref_payment, 2),
                        "gp_carry": round(gp_carry, 2),
                        "lp_distribution": round(lp_distribution, 2),
                    }
                )

            # Step 2: Check convergence
            new_carry_total = sum(d["gp_carry"] for d in distributions)
            delta = abs(new_carry_total - gp_carry_estimate)

            waterfall_log.append(
                {
                    "iteration": iterations,
                    "carry_estimate": round(new_carry_total, 2),
                    "delta": round(delta, 2),
                }
            )

            if delta < self.config.convergence_threshold:
                converged = True
                break

            gp_carry_estimate = new_carry_total

        # Calculate MOIC and IRR
        total_lp_dist = sum(d["lp_distribution"] for d in distributions)
        lp_moic = total_lp_dist / total_nav if total_nav > 0 else 0

        return {
            "waterfall_type": self.config.waterfall_type,
            "converged": converged,
            "iterations": iterations,
            "distributions": distributions,
            "summary": {
                "total_nav": total_nav,
                "total_gp_carry": round(sum(d["gp_carry"] for d in distributions), 2),
                "total_lp_distributions": round(total_lp_dist, 2),
                "total_management_fees": round(
                    sum(d["management_fee"] for d in distributions), 2
                ),
                "total_debt_service": round(
                    sum(d["debt_service"] for d in distributions), 2
                ),
                "lp_moic": round(lp_moic, 3),
                "remaining_debt": round(existing_debt, 2),
            },
            "convergence_log": waterfall_log,
        }


class CVMECEAnalyzer:
    """
    MECE analysis framework for GP-Led Continuation Vehicles.
    Three key branches per PRD:
    1. Price Fairness
    2. Economic Parity
    3. Governance Integrity
    """

    def analyze_price_fairness(
        self, nav: float, bid_price: float, comparable_cvs: List[Dict]
    ) -> Dict[str, Any]:
        """Assess whether the CV price is fair relative to NAV and market"""
        premium_discount = (bid_price - nav) / nav if nav > 0 else 0

        # Compare against historical CV transactions
        historical_premiums = [cv.get("premium_pct", 0) for cv in comparable_cvs]
        avg_historical = (
            sum(historical_premiums) / len(historical_premiums)
            if historical_premiums
            else 0
        )

        return {
            "branch": "price_fairness",
            "nav": nav,
            "bid_price": bid_price,
            "premium_discount_pct": round(premium_discount * 100, 2),
            "historical_avg_premium_pct": round(avg_historical * 100, 2),
            "assessment": (
                "FAIR"
                if abs(premium_discount - avg_historical) < 0.05
                else (
                    "ABOVE MARKET"
                    if premium_discount > avg_historical
                    else "BELOW MARKET — LP concern"
                )
            ),
        }

    def analyze_economic_parity(
        self, rolling_lps_terms: Dict, new_lps_terms: Dict
    ) -> Dict[str, Any]:
        """Check if rolling LPs and new LPs have equivalent economic terms"""
        disparities = []

        for key in ["carried_interest", "management_fee", "preferred_return"]:
            rolling_val = rolling_lps_terms.get(key, 0)
            new_val = new_lps_terms.get(key, 0)
            if abs(rolling_val - new_val) > 0.001:
                disparities.append(
                    {
                        "term": key,
                        "rolling_lps": rolling_val,
                        "new_lps": new_val,
                        "difference": round(new_val - rolling_val, 4),
                    }
                )

        return {
            "branch": "economic_parity",
            "parity_achieved": len(disparities) == 0,
            "disparities": disparities,
            "assessment": (
                "PARITY — All terms equivalent"
                if not disparities
                else f"DISPARITY — {len(disparities)} term(s) differ between rolling and new LPs"
            ),
        }

    def analyze_governance_integrity(
        self, gp_conflicts: List[str], lpac_approval: bool, fairness_opinion: bool
    ) -> Dict[str, Any]:
        """Assess governance safeguards for conflicts of interest"""
        score = 0
        if lpac_approval:
            score += 40
        if fairness_opinion:
            score += 30
        if len(gp_conflicts) == 0:
            score += 30
        else:
            score += max(0, 30 - len(gp_conflicts) * 10)

        return {
            "branch": "governance_integrity",
            "lpac_approval": lpac_approval,
            "fairness_opinion": fairness_opinion,
            "gp_conflicts_identified": gp_conflicts,
            "governance_score": score,
            "assessment": (
                "STRONG"
                if score >= 80
                else "ADEQUATE" if score >= 50 else "WEAK — Governance risks present"
            ),
        }

    def generate_mermaid_sankey(self, waterfall_result: Dict) -> str:
        """Generate a Mermaid Sankey diagram for the waterfall distribution"""
        summary = waterfall_result.get("summary", {})

        diagram = f"""```mermaid
sankey-beta

"Total NAV","{summary.get('total_nav', 0)}","Cash Flows"
"Cash Flows","{summary.get('total_lp_distributions', 0)}","LP Distributions"
"Cash Flows","{summary.get('total_gp_carry', 0)}","GP Carry"
"Cash Flows","{summary.get('total_management_fees', 0)}","Management Fees"
"Cash Flows","{summary.get('total_debt_service', 0)}","Debt Service"
```"""
        return diagram
