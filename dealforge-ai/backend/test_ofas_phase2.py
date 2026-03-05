"""
OFAS Phase 2 — Valuation & Comps Unit Tests
Run with: python test_ofas_phase2.py
"""

import sys
import os
import json

passed = 0
failed = 0
errors = []

sys.path.insert(0, r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend")


def test(name, func):
    global passed, failed
    try:
        func()
        print(f"  [PASS] {name}")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        failed += 1
        errors.append((name, str(e)))


# ============================================================
# Test 1: Comparable Companies Tool
# ============================================================
print("\nComparable Companies Tool")
print("=" * 55)

try:
    from app.core.tools.valuation_tools import (
        FetchComparableCompaniesTool,
        GICS_SECTOR_PEERS,
    )

    def test_comps_sector_defaults():
        tool = FetchComparableCompaniesTool()
        result = tool.execute(
            ticker="MSFT",
            sector="technology",
            target_metrics={"revenue": 200_000, "ebitda": 80_000, "net_income": 60_000},
        )
        assert result.success, result.error
        assert result.data["sector"] == "technology"
        assert result.data["peer_count"] >= 5
        assert "quartile_stats" in result.data
        assert "ev_revenue" in result.data["quartile_stats"]
        assert "median" in result.data["quartile_stats"]["ev_revenue"]
        # Should have implied valuations
        assert "implied_valuations" in result.data
        assert "ev_revenue" in result.data["implied_valuations"]

    def test_comps_with_explicit_peers():
        tool = FetchComparableCompaniesTool()
        result = tool.execute(
            ticker="CRM",
            sector="technology",
            peer_tickers=["NOW", "WDAY", "TEAM", "HUBS"],
        )
        assert result.success

    def test_comps_unknown_sector():
        tool = FetchComparableCompaniesTool()
        result = tool.execute(ticker="XYZ", sector="alien_tech")
        assert not result.success
        assert "Unknown sector" in result.error

    def test_comps_quartile_math():
        tool = FetchComparableCompaniesTool()
        stats = tool._compute_quartile_stats(
            [
                {"ev_revenue": 3.0, "ev_ebitda": 10.0, "pe": 15.0},
                {"ev_revenue": 5.0, "ev_ebitda": 14.0, "pe": 20.0},
                {"ev_revenue": 7.0, "ev_ebitda": 18.0, "pe": 25.0},
                {"ev_revenue": 9.0, "ev_ebitda": 22.0, "pe": 30.0},
            ]
        )
        assert stats["ev_revenue"]["median"] == 6.0
        assert stats["ev_revenue"]["min"] == 3.0
        assert stats["ev_revenue"]["max"] == 9.0

    def test_sector_coverage():
        assert len(GICS_SECTOR_PEERS) >= 6
        assert "technology" in GICS_SECTOR_PEERS
        assert "healthcare" in GICS_SECTOR_PEERS
        assert "energy" in GICS_SECTOR_PEERS

    test("Comps with sector defaults + implied valuations", test_comps_sector_defaults)
    test("Comps with explicit peer tickers", test_comps_with_explicit_peers)
    test("Comps with unknown sector", test_comps_unknown_sector)
    test("Quartile statistics math", test_comps_quartile_math)
    test("Sector coverage (6+ sectors)", test_sector_coverage)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 2: Football Field Tool
# ============================================================
print("\nFootball Field Tool")
print("=" * 55)

try:
    from app.core.tools.valuation_tools import GenerateFootballFieldTool

    def test_football_field_basic():
        tool = GenerateFootballFieldTool()
        result = tool.execute(
            ticker="MSFT",
            valuation_ranges={
                "DCF": {"low": 300_000, "mid": 400_000, "high": 500_000},
                "EV/EBITDA Comps": {"low": 280_000, "mid": 380_000, "high": 480_000},
                "Precedent Transactions": {
                    "low": 350_000,
                    "mid": 420_000,
                    "high": 520_000,
                },
            },
            current_price=400.0,
            shares_outstanding=7_500,
        )
        assert result.success, result.error
        data = result.data
        assert data["methodology_count"] == 3
        assert len(data["methods"]) == 3
        assert "composite_range" in data
        assert data["composite_range"]["low"] == 280_000
        assert data["composite_range"]["high"] == 520_000
        assert "upside_to_mid" in data
        assert "composite_per_share" in data

    def test_football_field_per_share():
        tool = GenerateFootballFieldTool()
        result = tool.execute(
            ticker="AAPL",
            valuation_ranges={
                "DCF": {"low": 2_500_000, "mid": 3_000_000, "high": 3_500_000},
            },
            shares_outstanding=15_000,
        )
        assert result.success
        assert result.data["composite_per_share"]["mid"] == 200.0

    def test_football_field_no_ranges():
        tool = GenerateFootballFieldTool()
        result = tool.execute(ticker="X", valuation_ranges={})
        assert not result.success

    test("Football field with 3 methodologies", test_football_field_basic)
    test("Football field per-share conversion", test_football_field_per_share)
    test("Football field with no ranges", test_football_field_no_ranges)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 3: Sensitivity Analysis Tool
# ============================================================
print("\nSensitivity Analysis Tool")
print("=" * 55)

try:
    from app.core.tools.valuation_tools import RunSensitivityAnalysisTool

    def test_sensitivity_dcf():
        tool = RunSensitivityAnalysisTool()
        result = tool.execute(
            analysis_type="dcf_wacc_growth",
            base_inputs={
                "projected_fcf": [100, 110, 120, 130, 140],
                "wacc": 0.10,
                "terminal_growth": 0.025,
            },
            row_variable={"name": "wacc", "values": [0.08, 0.10, 0.12, 0.14]},
            col_variable={"name": "terminal_growth", "values": [0.01, 0.025, 0.04]},
        )
        assert result.success, result.error
        data = result.data
        assert data["analysis_type"] == "dcf_wacc_growth"
        assert len(data["table"]) == 4  # 4 rows (WACC values)
        assert len(data["table"][0]) == 3  # 3 cols (growth values)
        # Lower WACC + higher growth = higher EV
        assert data["table"][0][2] > data["table"][3][0]
        # base_case should be identified
        assert data["base_case"]["value"] is not None

    def test_sensitivity_comps():
        tool = RunSensitivityAnalysisTool()
        result = tool.execute(
            analysis_type="comps_multiple_metric",
            base_inputs={},
            row_variable={"name": "multiple", "values": [8, 10, 12, 14]},
            col_variable={"name": "metric", "values": [5000, 6000, 7000]},
        )
        assert result.success
        # 10x * 6000 = 60000
        assert result.data["table"][1][1] == 60000.0

    def test_sensitivity_lbo():
        tool = RunSensitivityAnalysisTool()
        result = tool.execute(
            analysis_type="lbo_entry_exit",
            base_inputs={
                "ebitda_entry": 100,
                "ebitda_exit": 120,
                "equity_pct": 0.4,
                "holding_years": 5,
                "debt_paydown": 100,
            },
            row_variable={"name": "entry_multiple", "values": [8, 10, 12]},
            col_variable={"name": "exit_multiple", "values": [10, 12, 14]},
        )
        assert result.success
        table = result.data["table"]
        # Higher exit multiple should give higher IRR
        assert table[0][2] > table[0][0]  # Same entry, higher exit = higher IRR
        # Higher entry multiple should give lower IRR
        assert table[0][1] > table[2][1]  # Same exit, lower entry = higher IRR

    def test_sensitivity_invalid_wacc_growth():
        """When WACC <= growth, DCF should return None"""
        tool = RunSensitivityAnalysisTool()
        result = tool.execute(
            analysis_type="dcf_wacc_growth",
            base_inputs={"projected_fcf": [100, 110]},
            row_variable={"name": "wacc", "values": [0.02]},
            col_variable={"name": "terminal_growth", "values": [0.03]},
        )
        assert result.success
        assert result.data["table"][0][0] is None  # Invalid: WACC < growth

    test("DCF sensitivity (WACC x Growth)", test_sensitivity_dcf)
    test("Comps sensitivity (Multiple x Metric)", test_sensitivity_comps)
    test("LBO sensitivity (Entry x Exit multiples)", test_sensitivity_lbo)
    test("DCF invalid WACC < Growth returns None", test_sensitivity_invalid_wacc_growth)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 4: Tool Registration
# ============================================================
print("\nTool Registration")
print("=" * 55)

try:
    from app.core.tools.tool_router import ToolRouter, AGENT_TOOL_MAP

    def test_valuation_agent_tools():
        allowed = AGENT_TOOL_MAP.get("valuation_agent", [])
        assert "fetch_comparable_companies" in allowed
        assert "generate_football_field" in allowed
        assert "run_sensitivity_analysis" in allowed

    def test_dcf_architect_tools():
        allowed = AGENT_TOOL_MAP.get("dcf_lbo_architect", [])
        assert "excel_model_populate" in allowed
        assert "excel_export_tables" in allowed
        assert "run_sensitivity_analysis" in allowed

    test(
        "Valuation agent has comps + football + sensitivity tools",
        test_valuation_agent_tools,
    )
    test("DCF architect has Excel + sensitivity tools", test_dcf_architect_tools)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 55)
print(f"Results: {passed} passed, {failed} failed")
if errors:
    print("\nFailed tests:")
    for name, err in errors:
        print(f"  - {name}: {err}")
print("=" * 55)

sys.exit(0 if failed == 0 else 1)
