"""
ESG & Sustainability Tools for DealForge AI.

Specialized tools to extract carbon footprint data, flag supply chain risks,
and generate composite ESG scores during M&A diligence.
"""

from typing import Dict, Any, Optional
import structlog
from app.core.tools.tool_router import BaseTool, ToolResult
import re

logger = structlog.get_logger(__name__)


class CarbonFootprintExtractorTool(BaseTool):
    """Extracts Scope 1/2/3 emissions data from sustainability texts."""

    def __init__(self):
        super().__init__(
            name="carbon_footprint_extractor",
            description=(
                "Extracts Scope 1, 2, and 3 GHG emissions data from sustainability reports "
                "or text summaries using NLP profiling techniques."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "sustainability_text": {
                    "type": "string",
                    "description": "Text body containing the target's sustainability or CSR report.",
                },
            },
            "required": ["sustainability_text"],
        }

    async def execute(self, sustainability_text: str = "", **kwargs) -> ToolResult:
        text = sustainability_text.lower()

        # Simplified regex extraction for demonstration / mock logic
        def extract_number(pattern, txt):
            match = re.search(pattern, txt)
            if match:
                val_str = match.group(1).replace(",", "")
                try:
                    return float(val_str)
                except:
                    return 0.0
            return 0.0

        # Look for patterns like "Scope 1: 50,000 tons" or "scope 1 emissions of 1500"
        scope1 = extract_number(r"scope 1.*?([\d,]+)", text)
        scope2 = extract_number(r"scope 2.*?([\d,]+)", text)
        scope3 = extract_number(r"scope 3.*?([\d,]+)", text)

        total = scope1 + scope2 + scope3

        risk_level = "Low"
        if total > 100_000:
            risk_level = "High"
        elif total > 10_000:
            risk_level = "Medium"

        return ToolResult(
            success=True,
            data={
                "scope1_tco2e": scope1,
                "scope2_tco2e": scope2,
                "scope3_tco2e": scope3,
                "total_tco2e": total,
                "emissions_risk_level": risk_level,
                "note": (
                    "Extracted via statistical parsing of provided text."
                    if total > 0
                    else "No discrete emission tonnages found."
                ),
            },
        )


class SupplyChainRiskFlaggerTool(BaseTool):
    """Flags ethical and environmental risks in supplier docs."""

    def __init__(self):
        super().__init__(
            name="supply_chain_risk_flagger",
            description=(
                "Flags environmental, ethical, and forced labor risks based on provided "
                "supplier documentation or text summaries."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "supplier_text": {
                    "type": "string",
                    "description": "Text describing the target's supply chain or manufacturing footprint.",
                },
            },
            "required": ["supplier_text"],
        }

    async def execute(self, supplier_text: str = "", **kwargs) -> ToolResult:
        text = supplier_text.lower()

        risk_flags = []
        severity = "Low"

        if (
            "overseas" in text
            or "sweatshop" in text
            or "un-audited" in text
            or "no audited" in text
        ):
            risk_flags.append("Potential un-audited labor in overseas manufacturing.")
            severity = "High"

        if "forced labor" in text or "xinjiang" in text:
            risk_flags.append("Critical forced labor exposure detected.")
            severity = "Critical"

        if "conflict mineral" in text or "cobalt" in text:
            risk_flags.append("Exposure to conflict minerals supply chain.")
            severity = max(severity, "Medium")

        if not risk_flags:
            risk_flags.append(
                "No immediate supply chain risks detected in the provided text."
            )

        return ToolResult(
            success=True,
            data={
                "identified_risks": risk_flags,
                "supply_chain_risk_severity": severity,
            },
        )


class ESGScorerTool(BaseTool):
    """Computes a composite MSCI-style ESG score and NPV impact."""

    def __init__(self):
        super().__init__(
            name="esg_scorer",
            description=(
                "Computes a composite ESG score (0-10) and simulates financial impacts "
                "such as carbon tax. Requires inputs from carbon extractor and risk flagger."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "total_emissions": {
                    "type": "number",
                    "description": "Total Scope 1/2/3 emissions in tCO2e.",
                },
                "supply_chain_severity": {
                    "type": "string",
                    "description": "Severity from SupplyChainRiskFlaggerTool (Low, Medium, High, Critical).",
                },
            },
            "required": ["total_emissions", "supply_chain_severity"],
        }

    async def execute(
        self, total_emissions: float = 0.0, supply_chain_severity: str = "Low", **kwargs
    ) -> ToolResult:
        # Environmental calculation (0-10)
        env_score = 10.0
        if total_emissions > 100_000:
            env_score = 2.0
        elif total_emissions > 10_000:
            env_score = 5.0
        elif total_emissions > 0:
            env_score = 8.0

        # Social / Governance Calculation (0-10)
        soc_gov_score = 10.0
        if supply_chain_severity == "Critical":
            soc_gov_score = 1.0
        elif supply_chain_severity == "High":
            soc_gov_score = 3.0
        elif supply_chain_severity == "Medium":
            soc_gov_score = 6.0

        # Weighted Total: E(40%), S(30%), G(30%) - grouping S/G here for simplicity
        composite_score = (env_score * 0.4) + (soc_gov_score * 0.6)

        msci_rating = "AAA"
        if composite_score < 3:
            msci_rating = "CCC"
        elif composite_score < 5:
            msci_rating = "B"
        elif composite_score < 7:
            msci_rating = "BBB"
        elif composite_score < 8.5:
            msci_rating = "AA"

        # Financial Impact Bridge (Carbon Tax at $50/ton assumed)
        carbon_tax_cost = total_emissions * 50.0

        return ToolResult(
            success=True,
            data={
                "composite_esg_score": round(composite_score, 1),
                "simulated_msci_rating": msci_rating,
                "sub_scores": {
                    "environmental": round(env_score, 1),
                    "social_governance": round(soc_gov_score, 1),
                },
                "financial_impact_bridge": {
                    "carbon_tax_exposure_50_usd": f"-${carbon_tax_cost:,.2f}"
                },
            },
        )
