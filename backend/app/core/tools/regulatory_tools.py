"""
Regulatory & Cyber Tools for DealForge AI.

Specialized tools to perform automated cybersecurity audits, GDPR/privacy mapping,
and HHI Antitrust calculations.
"""

from typing import Dict, Any, List, Optional
import structlog
from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class CyberVulnScannerTool(BaseTool):
    """Detects vulnerabilities in security policies via regex/keyword mapping."""

    def __init__(self):
        super().__init__(
            name="cyber_vuln_scanner",
            description=(
                "Scans security policies or technical text for vulnerabilities like "
                "missing SOC2 compliance, previous data breaches, or ransomware risks."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "security_text": {
                    "type": "string",
                    "description": "Text describing the target company's cybersecurity posture or history.",
                },
            },
            "required": ["security_text"],
        }

    async def execute(self, security_text: str = "", **kwargs) -> ToolResult:
        text = security_text.lower()

        vulns = []
        vuln_count = 0
        remediation_cost = 0

        if "breach" in text or "hacked" in text or "compromised" in text:
            vulns.append("Historical data breach or compromise detected.")
            vuln_count += 1
            remediation_cost += 500_000

        if "ransomware" in text:
            vulns.append("Target has experienced or is actively exposed to ransomware.")
            vuln_count += 1
            remediation_cost += 1_000_000

        if "no soc2" in text or "lack of soc2" in text or "not soc2 compliant" in text:
            vulns.append("Missing SOC2 Type II compliance.")
            vuln_count += 1
            remediation_cost += 100_000

        compliance_flags = (
            "High Risk"
            if vuln_count > 1
            else ("Medium Risk" if vuln_count == 1 else "Low Risk")
        )

        return ToolResult(
            success=True,
            data={
                "vulnerabilities_detected": vulns,
                "vulnerabilities_count": vuln_count,
                "remediation_cost_estimate_usd": remediation_cost,
                "compliance_flags": compliance_flags,
            },
        )


class AntitrustHHICalculatorTool(BaseTool):
    """Computes Herfindahl-Hirschman Index (HHI) for antitrust risk."""

    def __init__(self):
        super().__init__(
            name="antitrust_hhi_calculator",
            description=(
                "Computes the Herfindahl-Hirschman Index (HHI) to estimate antitrust "
                "risk. Requires an array of decimal market shares (e.g., [0.40, 0.20])."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "market_shares": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of top firm market shares as decimals, e.g., [0.40, 0.20, 0.15].",
                },
            },
            "required": ["market_shares"],
        }

    async def execute(self, market_shares: List[float] = None, **kwargs) -> ToolResult:
        if not market_shares:
            return ToolResult(
                success=False, data=None, error="No market shares provided"
            )

        # HHI = Sum of squared market shares (where share is a whole number %, but input is decimal)
        # So we multiply decimal by 100, square it. Equivalently: decimal^2 * 10000.
        try:
            hhi = sum((share * 100) ** 2 for share in market_shares)
        except Exception as e:
            return ToolResult(
                success=False, data=None, error=f"Invalid share data: {str(e)}"
            )

        classification = "Low"
        probability = "Highly Probable (Safe Harbor)"

        if hhi > 2500:
            classification = "High Concentration"
            probability = "Low (Highly Scrutinized by FTC/DOJ)"
        elif hhi > 1500:
            classification = "Moderate Concentration"
            probability = "Moderate (May require concessions)"

        return ToolResult(
            success=True,
            data={
                "calculated_hhi": round(hhi, 2),
                "risk_classification": classification,
                "clearance_probability": probability,
            },
        )


class PrivacyAuditorTool(BaseTool):
    """Flags high-risk data localization and privacy compliance issues."""

    def __init__(self):
        super().__init__(
            name="privacy_auditor",
            description=(
                "Maps data flows based on input text and flags GDPR / Schrems II "
                "exposures regarding international data transfers."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "data_flow_text": {
                    "type": "string",
                    "description": "Text detailing the target's data storage locations and EU/US data flows.",
                },
            },
            "required": ["data_flow_text"],
        }

    async def execute(self, data_flow_text: str = "", **kwargs) -> ToolResult:
        text = data_flow_text.lower()

        issues = []
        is_eu = (
            "eu " in text or "europe" in text or "european" in text or "gdpr" in text
        )
        is_us = "us " in text or "united states" in text or "america " in text

        if is_eu and is_us and ("store" in text or "transfer" in text):
            # Check for Schrems II / standard contractual clauses logic
            if "scc" not in text and "standard contractual clauses" not in text:
                issues.append(
                    "Potential Schrems II violation: EU data transferred to US without explicit SCCs or Data Privacy Framework mentions."
                )

        if "gdpr" in text and "no dpo" in text:
            issues.append(
                "Missing Data Protection Officer (DPO) despite GDPR exposure."
            )

        if not issues:
            issues.append(
                "No explicit cross-border or privacy framework violations detected."
            )

        return ToolResult(
            success=True,
            data={
                "privacy_audit_findings": issues,
                "audit_status": (
                    "Failed"
                    if len(issues) > 0 and "No explicit" not in issues[0]
                    else "Passed"
                ),
            },
        )
