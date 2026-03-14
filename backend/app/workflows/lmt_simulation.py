"""Liability Management (LMT) Stressed Borrower Simulation for DealForge AI

Per the PRD, this module implements:
1. Loophole Detection: Drop-downs, double dips, up-tiers
2. Monte Carlo Recovery Modeling: 10,000 iterations with standard error convergence
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import random
import math
import re
import structlog

logger = structlog.get_logger()


@dataclass
class LMTConfig:
    """Configuration for LMT simulation"""

    num_simulations: int = 10_000
    confidence_level: float = 0.95
    recovery_rate_mean: float = 0.40
    recovery_rate_std: float = 0.20
    lgd_correlation: float = 0.30
    random_seed: Optional[int] = 42


class LoopholeDetector:
    """
    Detects liability management loopholes in credit agreements.
    Scans for structural subordination techniques used by distressed borrowers.
    """

    LOOPHOLE_PATTERNS = [
        {
            "name": "drop_down",
            "description": "Transfer of assets to unrestricted subsidiaries to move collateral out of creditor reach",
            "patterns": [
                r"unrestricted\s+subsidiar",
                r"designated\s+(?:as\s+)?unrestricted",
                r"transfer\s+(?:to|of)\s+(?:assets?\s+to\s+)?(?:a\s+)?unrestricted",
                r"investment\s+(?:in|to)\s+unrestricted",
            ],
        },
        {
            "name": "double_dip",
            "description": "Same collateral pool pledged to multiple tranches, giving structural priority to favored lenders",
            "patterns": [
                r"cross[- ]?collateral",
                r"shared\s+(?:collateral|security)",
                r"pari\s+passu\s+(?:lien|claim)",
                r"equal\s+(?:and\s+)?ratable",
            ],
        },
        {
            "name": "up_tier",
            "description": "Priming existing lenders by issuing new super-senior debt via consent of a subset of lenders",
            "patterns": [
                r"super[- ]?senior",
                r"priming\s+(?:lien|debt|facility)",
                r"(?:first|1st)\s+out\s+(?:/|and)\s+(?:last|2nd)\s+out",
                r"roll[- ]?up\s+(?:transaction|facility)",
                r"non[- ]?pro[- ]?rata",
            ],
        },
        {
            "name": "asset_stripping",
            "description": "Transferring valuable intellectual property or assets to entities beyond creditor reach",
            "patterns": [
                r"(?:ip|intellectual\s+property)\s+(?:transfer|assignment|license)",
                r"sale[- ]?leaseback",
                r"dividend\s+(?:from|out\s+of)\s+(?:restricted\s+)?(?:subsidiary|assets?)",
            ],
        },
        {
            "name": "covenant_erosion",
            "description": "Progressive weakening of protective covenants through amendments or waivers",
            "patterns": [
                r"covenant[- ]?lite",
                r"waiver\s+of\s+(?:default|covenant)",
                r"amendment\s+(?:to\s+)?(?:permit|allow)",
                r"basket\s+(?:increase|expansion)",
            ],
        },
    ]

    def __init__(self):
        self.logger = structlog.get_logger(component="loophole_detector")

    def scan(self, agreement_text: str) -> List[Dict[str, Any]]:
        """
        Scan a credit agreement for LMT loopholes.

        Args:
            agreement_text: Full text of the credit agreement, indenture, or LPA

        Returns:
            List of detected loopholes with context and severity
        """
        findings = []
        text_lower = agreement_text.lower()

        for loophole in self.LOOPHOLE_PATTERNS:
            for pattern in loophole["patterns"]:
                matches = list(re.finditer(pattern, text_lower))
                for match in matches:
                    # Get surrounding context
                    start = max(0, match.start() - 100)
                    end = min(len(agreement_text), match.end() + 100)
                    context = agreement_text[start:end].strip()

                    findings.append(
                        {
                            "loophole_type": loophole["name"],
                            "description": loophole["description"],
                            "matched_text": match.group(),
                            "context": context,
                            "position": match.start(),
                            "severity": self._assess_severity(
                                loophole["name"], context
                            ),
                        }
                    )

        # Deduplicate by position proximity
        findings = self._deduplicate(findings)

        self.logger.info(
            "Loophole scan complete",
            total_findings=len(findings),
            types_found=list(set(f["loophole_type"] for f in findings)),
        )

        return findings

    def _assess_severity(self, loophole_type: str, context: str) -> int:
        """Assess severity (1-5) based on loophole type and context"""
        severity_map = {
            "up_tier": 5,
            "drop_down": 4,
            "double_dip": 4,
            "asset_stripping": 4,
            "covenant_erosion": 3,
        }
        return severity_map.get(loophole_type, 2)

    def _deduplicate(self, findings: List[Dict], proximity: int = 200) -> List[Dict]:
        """Remove duplicate findings within close proximity"""
        if not findings:
            return findings

        findings.sort(key=lambda f: f["position"])
        deduped = [findings[0]]

        for f in findings[1:]:
            if (
                f["position"] - deduped[-1]["position"] > proximity
                or f["loophole_type"] != deduped[-1]["loophole_type"]
            ):
                deduped.append(f)

        return deduped


class MonteCarloRecoveryModel:
    """
    Monte Carlo simulation for recovery rate modeling.
    Runs N iterations to estimate recovery distributions for distressed debt.
    """

    def __init__(self, config: LMTConfig = None):
        self.config = config or LMTConfig()
        self.logger = structlog.get_logger(component="monte_carlo_recovery")
        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

    def simulate(
        self,
        outstanding_debt: float,
        collateral_value: float,
        seniority_rank: int = 1,  # 1 = most senior
        total_tranches: int = 3,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation for recovery estimates.

        Args:
            outstanding_debt: Total outstanding debt for this tranche
            collateral_value: Estimated collateral value
            seniority_rank: Position in the capital structure (1 = senior)
            total_tranches: Total debt tranches

        Returns:
            Distribution statistics and percentile analysis
        """
        recoveries = []
        recovery_rates = []

        # Seniority adjustment: senior tranches recover more
        seniority_factor = 1 - ((seniority_rank - 1) / total_tranches * 0.5)

        for _ in range(self.config.num_simulations):
            # Sample recovery rate from a truncated normal distribution
            raw_rate = random.gauss(
                self.config.recovery_rate_mean * seniority_factor,
                self.config.recovery_rate_std,
            )
            recovery_rate = max(0.0, min(1.0, raw_rate))

            # Apply collateral coverage ratio
            if collateral_value > 0:
                coverage_ratio = collateral_value / outstanding_debt
                recovery_rate = min(recovery_rate, coverage_ratio)

            recovery_amount = outstanding_debt * recovery_rate
            recoveries.append(recovery_amount)
            recovery_rates.append(recovery_rate)

        # Calculate statistics
        recoveries.sort()
        rates_sorted = sorted(recovery_rates)
        n = len(recoveries)

        mean_recovery = sum(recoveries) / n
        mean_rate = sum(recovery_rates) / n
        std_recovery = math.sqrt(sum((r - mean_recovery) ** 2 for r in recoveries) / n)
        std_error = std_recovery / math.sqrt(n)

        # Percentiles
        def percentile(data, p):
            k = (len(data) - 1) * p / 100
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return data[int(k)]
            return data[f] * (c - k) + data[c] * (k - f)

        return {
            "simulations": self.config.num_simulations,
            "outstanding_debt": outstanding_debt,
            "collateral_value": collateral_value,
            "seniority_rank": seniority_rank,
            "statistics": {
                "mean_recovery": round(mean_recovery, 2),
                "mean_recovery_rate": round(mean_rate, 4),
                "std_deviation": round(std_recovery, 2),
                "standard_error": round(std_error, 2),
                "coefficient_of_variation": (
                    round(std_recovery / mean_recovery, 4) if mean_recovery > 0 else 0
                ),
            },
            "percentiles": {
                "p5": round(percentile(recoveries, 5), 2),
                "p10": round(percentile(recoveries, 10), 2),
                "p25": round(percentile(recoveries, 25), 2),
                "p50_median": round(percentile(recoveries, 50), 2),
                "p75": round(percentile(recoveries, 75), 2),
                "p90": round(percentile(recoveries, 90), 2),
                "p95": round(percentile(recoveries, 95), 2),
            },
            "recovery_rate_distribution": {
                "p5": round(percentile(rates_sorted, 5), 4),
                "p25": round(percentile(rates_sorted, 25), 4),
                "p50": round(percentile(rates_sorted, 50), 4),
                "p75": round(percentile(rates_sorted, 75), 4),
                "p95": round(percentile(rates_sorted, 95), 4),
            },
            "convergence": {
                "converged": std_error < (mean_recovery * 0.01),
                "standard_error_pct": (
                    round(std_error / mean_recovery * 100, 2)
                    if mean_recovery > 0
                    else 0
                ),
            },
        }

    def run_full_capital_structure(
        self,
        tranches: List[Dict[str, Any]],
        total_collateral: float,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo across the entire capital structure.

        Args:
            tranches: List of dicts with 'name', 'amount', 'seniority_rank'
            total_collateral: Total collateral pool value
        """
        results = {}
        remaining_collateral = total_collateral

        # Sort by seniority (most senior first)
        sorted_tranches = sorted(tranches, key=lambda t: t.get("seniority_rank", 1))

        for tranche in sorted_tranches:
            tranche_result = self.simulate(
                outstanding_debt=tranche["amount"],
                collateral_value=remaining_collateral,
                seniority_rank=tranche["seniority_rank"],
                total_tranches=len(tranches),
            )
            results[tranche["name"]] = tranche_result

            # Reduce available collateral for junior tranches
            remaining_collateral -= tranche_result["statistics"]["mean_recovery"]
            remaining_collateral = max(0, remaining_collateral)

        return {
            "capital_structure_analysis": results,
            "total_collateral": total_collateral,
            "total_debt": sum(t["amount"] for t in tranches),
            "overall_coverage_ratio": (
                round(total_collateral / sum(t["amount"] for t in tranches), 3)
                if sum(t["amount"] for t in tranches) > 0
                else 0
            ),
        }
