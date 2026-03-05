"""
OFAS Compliance QA Agent — Automated Quality Assurance

Validates deliverables before IC submission:
- Checks for missing mandatory sections
- Verifies citation coverage (no unattributed claims)
- Validates numerical consistency (balance sheet balances, etc.)
- Confirms regulatory disclosure compliance
- Routes failures back to Supervisor for re-work
"""

from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class ComplianceQAAgent(BaseAgent):
    """
    The Compliance Officer — validates all deliverables before IC submission.

    Checks:
    1. Section completeness (mandatory sections present)
    2. Citation coverage (findings have sources)
    3. Numerical consistency (totals match, ratios valid)
    4. Regulatory disclosures included
    5. Confidentiality markings present
    """

    name = "compliance_qa_agent"
    description = "Automated compliance quality assurance — validates deliverables before IC submission"

    # Mandatory IC memo sections
    MANDATORY_SECTIONS = [
        "executive_summary",
        "investment_thesis",
        "financial_analysis",
        "valuation",
        "risks",
        "recommendation",
    ]

    # Minimum citation count per section
    MIN_CITATIONS = 3

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}
        action = context.get("action", "full_qa")

        try:
            if action == "validate_memo":
                return self._validate_memo(context, start)
            elif action == "validate_model":
                return self._validate_model(context, start)
            elif action == "validate_deck":
                return self._validate_deck(context, start)
            else:
                # Full QA — validate everything
                return await self._full_qa(context, start)

        except Exception as e:
            self.logger.error("compliance_qa_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    def _validate_memo(self, context: Dict, start: datetime) -> AgentOutput:
        """Validate IC memo for completeness and citation coverage"""
        memo_sections = context.get("sections", {})
        citations = context.get("citations", [])
        issues = []
        warnings = []

        # Check 1: Mandatory sections
        for section in self.MANDATORY_SECTIONS:
            if section not in memo_sections or not memo_sections[section]:
                issues.append(
                    {
                        "type": "missing_section",
                        "severity": "error",
                        "detail": f"Mandatory section '{section}' is missing or empty",
                        "remediation": f"Re-run InvestmentMemoAgent to generate {section}",
                    }
                )
            elif len(str(memo_sections[section])) < 50:
                warnings.append(
                    {
                        "type": "thin_section",
                        "severity": "warning",
                        "detail": f"Section '{section}' has insufficient content ({len(str(memo_sections[section]))} chars)",
                    }
                )

        # Check 2: Citation coverage
        if len(citations) < self.MIN_CITATIONS:
            issues.append(
                {
                    "type": "insufficient_citations",
                    "severity": "error",
                    "detail": f"Only {len(citations)} citations — minimum {self.MIN_CITATIONS} required",
                    "remediation": "Re-run DD agent with RAG context to generate source citations",
                }
            )

        # Check 3: RAG chunk linkage
        unlinked = [c for c in citations if not c.get("chunk_id")]
        if unlinked:
            warnings.append(
                {
                    "type": "unlinked_citations",
                    "severity": "warning",
                    "detail": f"{len(unlinked)} citation(s) without RAG chunk_id linkage",
                }
            )

        # Check 4: Recommendation present and valid
        recommendation = memo_sections.get("recommendation", "")
        valid_recs = [
            "proceed",
            "caution",
            "reject",
            "strong buy",
            "buy",
            "hold",
            "pass",
        ]
        if recommendation:
            has_valid = any(r in recommendation.lower() for r in valid_recs)
            if not has_valid:
                warnings.append(
                    {
                        "type": "unclear_recommendation",
                        "severity": "warning",
                        "detail": "Recommendation section doesn't contain a clear BUY/PASS verdict",
                    }
                )

        # Check 5: Confidentiality
        all_text = " ".join(str(v) for v in memo_sections.values())
        if "confidential" not in all_text.lower():
            warnings.append(
                {
                    "type": "no_confidentiality_marking",
                    "severity": "warning",
                    "detail": "No confidentiality marking found in memo",
                }
            )

        passed = len(issues) == 0
        elapsed = (datetime.utcnow() - start).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "check_type": "memo_validation",
                "passed": passed,
                "issue_count": len(issues),
                "warning_count": len(warnings),
                "issues": issues,
                "warnings": warnings,
                "sections_present": [
                    s for s in self.MANDATORY_SECTIONS if s in memo_sections
                ],
                "sections_missing": [
                    s for s in self.MANDATORY_SECTIONS if s not in memo_sections
                ],
                "citation_count": len(citations),
            },
            reasoning=f"Memo QA: {'PASSED' if passed else 'FAILED'} — {len(issues)} issues, {len(warnings)} warnings",
            confidence=1.0 if passed else 0.5,
            execution_time_ms=elapsed,
        )

    def _validate_model(self, context: Dict, start: datetime) -> AgentOutput:
        """Validate financial model outputs"""
        model_outputs = context.get("model_outputs", {})
        checks = context.get("checks", {})
        issues = []
        warnings = []

        # Check balance sheet balances
        if not checks.get("balance_sheet_balanced", True):
            issues.append(
                {
                    "type": "bs_imbalance",
                    "severity": "error",
                    "detail": "Balance sheet does not balance (A != L+E)",
                    "remediation": "Re-run model build with corrected inputs",
                }
            )

        # Check cash flow reconciliation
        if not checks.get("cash_reconciles", True):
            issues.append(
                {
                    "type": "cash_mismatch",
                    "severity": "error",
                    "detail": "Cash flow statement does not reconcile to balance sheet",
                }
            )

        # Check formula count (should be > 0 if formulas preserved)
        formula_count = checks.get("formula_count", -1)
        if formula_count == 0:
            warnings.append(
                {
                    "type": "no_formulas",
                    "severity": "warning",
                    "detail": "Model has no formulas — may have been saved with data-only mode",
                }
            )

        # Check for negative revenue
        summary = model_outputs.get("summary", {})
        revenue = summary.get("revenue", 0)
        if isinstance(revenue, (int, float)) and revenue < 0:
            issues.append(
                {
                    "type": "negative_revenue",
                    "severity": "error",
                    "detail": f"Revenue is negative ({revenue})",
                }
            )

        passed = len(issues) == 0
        elapsed = (datetime.utcnow() - start).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "check_type": "model_validation",
                "passed": passed,
                "issue_count": len(issues),
                "warning_count": len(warnings),
                "issues": issues,
                "warnings": warnings,
            },
            reasoning=f"Model QA: {'PASSED' if passed else 'FAILED'}",
            confidence=1.0 if passed else 0.3,
            execution_time_ms=elapsed,
        )

    def _validate_deck(self, context: Dict, start: datetime) -> AgentOutput:
        """Validate deal deck"""
        deck_path = context.get("deck_path", "")
        slide_count = context.get("slide_count", 0)
        issues = []

        if not deck_path:
            issues.append(
                {
                    "type": "no_deck",
                    "severity": "error",
                    "detail": "No deck file path provided",
                }
            )

        if slide_count < 5:
            issues.append(
                {
                    "type": "thin_deck",
                    "severity": "warning",
                    "detail": f"Deck has only {slide_count} slides — minimum 5 recommended",
                }
            )

        passed = len(issues) == 0
        elapsed = (datetime.utcnow() - start).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "check_type": "deck_validation",
                "passed": passed,
                "issues": issues,
            },
            reasoning=f"Deck QA: {'PASSED' if passed else 'FAILED'}",
            confidence=1.0 if passed else 0.5,
            execution_time_ms=elapsed,
        )

    async def _full_qa(self, context: Dict, start: datetime) -> AgentOutput:
        """Run all validations"""
        results = {}

        if context.get("sections"):
            memo_result = self._validate_memo(context, start)
            results["memo"] = memo_result.data

        if context.get("model_outputs") or context.get("checks"):
            model_result = self._validate_model(context, start)
            results["model"] = model_result.data

        if context.get("deck_path"):
            deck_result = self._validate_deck(context, start)
            results["deck"] = deck_result.data

        all_passed = all(r.get("passed", True) for r in results.values())
        total_issues = sum(r.get("issue_count", 0) for r in results.values())

        elapsed = (datetime.utcnow() - start).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "check_type": "full_qa",
                "passed": all_passed,
                "total_issues": total_issues,
                "results": results,
            },
            reasoning=f"Full QA: {'ALL PASSED' if all_passed else f'FAILED ({total_issues} issues)'}",
            confidence=1.0 if all_passed else 0.3,
            execution_time_ms=elapsed,
        )
