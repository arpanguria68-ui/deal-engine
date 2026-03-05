"""
Deterministic Output Validator for DealForge AI

Inspired by Anthropic's recalc.py approach: before an agent delivers any
structured output (Excel file, financial table), it runs validation to verify
mathematical consistency and catch formula errors.

This prevents hallucinated or inconsistent numbers reaching end users.
"""

from __future__ import annotations
import json
from typing import Any, Optional
import structlog

logger = structlog.get_logger()


class FinancialValidator:
    """
    Validates financial model outputs for mathematical consistency.
    Checks DCF bridges, LBO waterfalls, and accounting identities.
    """

    @staticmethod
    def validate_dcf_output(data: dict) -> dict:
        """
        Validate DCF model output for mathematical consistency.
        Returns: {"valid": bool, "errors": list, "warnings": list}
        """
        errors = []
        warnings = []

        try:
            # Extract values - be tolerant of missing keys
            pv_fcfs = data.get("pv_explicit_fcfs", 0) or 0
            pv_tv = data.get("pv_terminal_value", 0) or 0
            enterprise_value = data.get("enterprise_value", 0) or 0
            net_debt = data.get("net_debt", 0) or 0
            equity_value = data.get("equity_value", 0) or 0
            shares = data.get("diluted_shares", 0) or 0
            implied_price = data.get("implied_price_per_share", 0) or 0
            wacc = data.get("wacc", 0) or 0
            terminal_growth = data.get("terminal_growth_rate", 0) or 0

            # Check: EV = PV FCFs + PV Terminal Value (within 1% tolerance)
            if pv_fcfs and pv_tv and enterprise_value:
                calc_ev = pv_fcfs + pv_tv
                if (
                    abs(calc_ev - enterprise_value) / max(abs(enterprise_value), 1)
                    > 0.01
                ):
                    errors.append(
                        f"EV bridge mismatch: PV FCFs ({pv_fcfs:,.0f}) + PV TV ({pv_tv:,.0f}) "
                        f"= {calc_ev:,.0f} but reported EV = {enterprise_value:,.0f}"
                    )

            # Check: Equity Value = EV - Net Debt
            if enterprise_value and equity_value:
                calc_equity = enterprise_value - net_debt
                if abs(calc_equity - equity_value) / max(abs(equity_value), 1) > 0.01:
                    errors.append(
                        f"Equity bridge mismatch: EV ({enterprise_value:,.0f}) - Net Debt "
                        f"({net_debt:,.0f}) = {calc_equity:,.0f} but reported equity = {equity_value:,.0f}"
                    )

            # Check: Implied Price = Equity Value / Shares
            if equity_value and shares and implied_price:
                calc_price = equity_value / shares
                if abs(calc_price - implied_price) / max(abs(implied_price), 1) > 0.02:
                    errors.append(
                        f"Price per share mismatch: {equity_value:,.0f} / {shares:,.0f} "
                        f"= {calc_price:.2f} but reported {implied_price:.2f}"
                    )

            # Warning: Terminal growth > WACC (creates infinite/negative value)
            if wacc and terminal_growth and terminal_growth >= wacc:
                errors.append(
                    f"CRITICAL: Terminal growth rate ({terminal_growth:.1%}) >= WACC ({wacc:.1%}). "
                    "This creates infinite or negative enterprise value."
                )

            # Warning: TV proportion check
            if pv_tv and enterprise_value and enterprise_value > 0:
                tv_pct = pv_tv / enterprise_value
                if tv_pct > 0.80:
                    warnings.append(
                        f"Terminal value is {tv_pct:.0%} of EV. Consider if terminal assumptions are realistic."
                    )

        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "check_count": 5,
        }

    @staticmethod
    def validate_lbo_output(data: dict) -> dict:
        """Validate LBO model output for mathematical consistency."""
        errors = []
        warnings = []

        try:
            entry_ev = data.get("entry_ev", 0) or 0
            total_debt = data.get("total_debt", 0) or 0
            sponsor_equity = data.get("sponsor_equity", 0) or 0
            exit_ev = data.get("exit_ev", 0) or 0
            remaining_debt = data.get("remaining_debt_at_exit", 0) or 0
            equity_proceeds = data.get("equity_proceeds", 0) or 0
            irr = data.get("irr", 0) or 0
            moic = data.get("moic", 0) or 0
            hold_period = data.get("hold_period_years", 5) or 5

            # Sources = Uses check
            if entry_ev and total_debt and sponsor_equity:
                sources = total_debt + sponsor_equity
                if abs(sources - entry_ev) / max(abs(entry_ev), 1) > 0.01:
                    errors.append(
                        f"Sources ({sources:,.0f}) ≠ Entry EV ({entry_ev:,.0f}). "
                        "Check debt + equity financing."
                    )

            # Equity proceeds check
            if exit_ev and remaining_debt and equity_proceeds:
                calc_proceeds = exit_ev - remaining_debt
                if (
                    abs(calc_proceeds - equity_proceeds) / max(abs(equity_proceeds), 1)
                    > 0.02
                ):
                    errors.append(
                        f"Equity proceeds mismatch: Exit EV ({exit_ev:,.0f}) - "
                        f"Remaining Debt ({remaining_debt:,.0f}) = {calc_proceeds:,.0f} "
                        f"but reported {equity_proceeds:,.0f}"
                    )

            # IRR vs MOIC cross-check (approximate)
            if irr and moic and hold_period:
                calc_moic = (1 + irr) ** hold_period
                if abs(calc_moic - moic) / max(abs(moic), 1) > 0.10:
                    warnings.append(
                        f"IRR ({irr:.1%}) and MOIC ({moic:.1f}x) are inconsistent for "
                        f"a {hold_period}-year hold. Check returns math."
                    )

        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def validate_financial_statement(data: dict) -> dict:
        """Validate IS/BS/CF statement accounting identities."""
        errors = []

        try:
            # Income Statement
            revenue = data.get("revenue", 0) or 0
            cogs = data.get("cogs", 0) or 0
            gross_profit = data.get("gross_profit", 0) or 0
            if revenue and cogs and gross_profit:
                calc_gp = revenue - cogs
                if abs(calc_gp - gross_profit) / max(abs(gross_profit), 1) > 0.01:
                    errors.append(
                        f"Gross Profit check: {revenue:,.0f} - {cogs:,.0f} = {calc_gp:,.0f} "
                        f"but reported {gross_profit:,.0f}"
                    )

            # Balance Sheet identity
            assets = data.get("total_assets", 0) or 0
            liabilities = data.get("total_liabilities", 0) or 0
            equity = data.get("total_equity", 0) or 0
            if assets and liabilities and equity:
                if abs(assets - liabilities - equity) / max(abs(assets), 1) > 0.01:
                    errors.append(
                        f"BS doesn't balance: Assets ({assets:,.0f}) ≠ "
                        f"Liabilities ({liabilities:,.0f}) + Equity ({equity:,.0f})"
                    )

        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return {"valid": len(errors) == 0, "errors": errors}


def validate_agent_output(output_type: str, data: dict) -> dict:
    """
    Main entry point: validate agent output before returning to user.
    output_type: "dcf" | "lbo" | "financial_statement"
    """
    validator = FinancialValidator()

    if output_type == "dcf":
        result = validator.validate_dcf_output(data)
    elif output_type == "lbo":
        result = validator.validate_lbo_output(data)
    elif output_type == "financial_statement":
        result = validator.validate_financial_statement(data)
    else:
        return {
            "valid": True,
            "errors": [],
            "warnings": ["No validator for output type: " + output_type],
        }

    if result["errors"]:
        logger.warning(
            "financial_validation_failed",
            output_type=output_type,
            errors=result["errors"],
        )
    else:
        logger.info("financial_validation_passed", output_type=output_type)

    return result


def format_validation_block(result: dict) -> str:
    """Format validation results as a readable block for chat output."""
    if result["valid"] and not result.get("warnings"):
        return "\n\n✅ **Validation Passed** — All mathematical checks verified."

    lines = []
    if result["valid"]:
        lines.append("\n\n⚠️ **Validation Passed with Warnings:**")
    else:
        lines.append("\n\n❌ **Validation Errors Detected** — Please review:")

    for err in result.get("errors", []):
        lines.append(f"- ❌ {err}")
    for warn in result.get("warnings", []):
        lines.append(f"- ⚠️ {warn}")

    return "\n".join(lines)
