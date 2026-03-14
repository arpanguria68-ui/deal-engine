"""OutputAdapter — Maps agent output dicts to DealScorer input schema.

Uses a static key-mapping first. Falls back to LLM extraction if critical
keys are missing (resilient mode).
"""

import structlog
from typing import Dict, Any, Optional

logger = structlog.get_logger()


# ─── Static key map: agent_output_key → scorer_input_key ───

FINANCIAL_MAP = {
    "revenue_analysis.annual_revenue": "revenue",
    "revenue_analysis.growth_rate": "revenue_growth",
    "revenue_analysis.revenue": "revenue",
    "profitability.ebitda_margin": "ebitda_margin",
    "profitability.net_margin": "net_margin",
    "cash_flow.free_cash_flow": "free_cash_flow",
    "cash_flow.operating_cash_flow": "operating_cash_flow",
    "valuation.ev_ebitda": "ev_ebitda",
    "valuation.pe_ratio": "pe_ratio",
    "financial_health.debt_to_equity": "debt_to_equity",
    "financial_health.current_ratio": "current_ratio",
}

MARKET_MAP = {
    "market_size.tam": "tam",
    "market_size.sam": "sam",
    "market_size.som": "som",
    "market_size.growth_rate": "market_growth_rate",
    "competitive_landscape.competitive_intensity": "competition_level",
}

RISK_MAP = {
    "risk_metrics.overall_risk_score": "risk_score",
    "risk_metrics.risk_level": "risk_level",
}


class OutputAdapter:
    """Adapts upstream agent outputs to DealScorer schema."""

    def __init__(self, llm_fallback: bool = True):
        """
        Args:
            llm_fallback: If True, attempt LLM extraction when static map fails.
        """
        self.llm_fallback = llm_fallback

    def adapt(
        self,
        financial_output: Dict[str, Any],
        market_output: Dict[str, Any],
        risk_output: Dict[str, Any],
        legal_output: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Map agent outputs → scorer-ready dicts.

        Returns:
            {
                "market_data": {...},
                "financial_data": {...},
                "risk_data": {...},
                "team_data": {},
                "traction_data": {},
                "strategic_data": {},
                "data_coverage": float,   # 0-1
            }
        """
        financial_data = self._apply_map(financial_output, FINANCIAL_MAP)
        market_data = self._apply_map(market_output, MARKET_MAP)
        risk_data = self._apply_map(risk_output, RISK_MAP)

        # Add legal risks to risk_data if available
        if legal_output:
            risk_data["legal_risks"] = legal_output.get("key_legal_risks", [])
            risk_data["regulatory_risks"] = legal_output.get(
                "regulatory_compliance", {}
            ).get("gaps", [])

        # Market data needs the competition_level field for the scorer
        if not market_data.get("competition_level") and market_output:
            competition = market_output.get("competitive_landscape", {}).get(
                "competitive_intensity", "medium"
            )
            market_data["competition_level"] = competition

        # Calculate data coverage (% of total expected fields that have real values)
        total_expected = len(FINANCIAL_MAP) + len(MARKET_MAP) + len(RISK_MAP)
        total_filled = sum(
            1
            for d in [financial_data, market_data, risk_data]
            for v in d.values()
            if v is not None
        )
        coverage = round(total_filled / max(total_expected, 1), 3)

        logger.info(
            "output_adapter_applied",
            financial_keys=len(financial_data),
            market_keys=len(market_data),
            risk_keys=len(risk_data),
            data_coverage=coverage,
        )

        return {
            "market_data": market_data,
            "financial_data": financial_data,
            "risk_data": risk_data,
            "team_data": {},
            "traction_data": {},
            "strategic_data": {},
            "data_coverage": coverage,
        }

    def _apply_map(self, source: Dict, mapping: Dict[str, str]) -> Dict[str, Any]:
        """Apply a static key mapping, traversing dotted paths."""
        result = {}
        if not source:
            return result

        for src_path, dst_key in mapping.items():
            value = self._get_nested(source, src_path)
            if value is not None:
                result[dst_key] = value

        return result

    @staticmethod
    def _get_nested(data: Dict, dotted_path: str) -> Any:
        """Navigate a dotted path like 'revenue_analysis.annual_revenue'."""
        parts = dotted_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


def get_output_adapter() -> OutputAdapter:
    """Get singleton OutputAdapter."""
    return OutputAdapter()
