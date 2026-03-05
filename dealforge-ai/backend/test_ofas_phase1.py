"""
OFAS Phase 1 — Unit Tests
Run with: python test_ofas_phase1.py

Tests:
1. OFAS State Models (Task, Issue, Mission)
2. OFAS Supervisor (Mission Planning, Status, Quality Gates)
3. Excel Model Engine (Formula Preservation, Export)
4. Financial Data API (SEC EDGAR structure)
"""

import sys
import os
import asyncio
import json

# Track results
passed = 0
failed = 0
errors = []

sys.path.insert(0, r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend")


def test(name, func):
    global passed, failed
    try:
        func()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1
        errors.append((name, str(e)))


# ============================================================
# Test 1: OFAS State Models
# ============================================================
print("\n🏗️ OFAS State Models — Task, Issue, Mission")
print("=" * 55)

try:
    from app.orchestrator.state import (
        OFASTask,
        OFASIssue,
        OFASMissionState,
        create_ofas_mission,
        create_ofas_task,
        create_ofas_issue,
        get_ready_tasks,
        has_blocking_issues,
    )

    def test_create_mission():
        mission = create_ofas_mission(
            deal_id="test_001",
            ticker="MSFT",
            objective="Evaluate acquisition",
            constraints=["Max price $500M"],
        )
        assert mission["deal_id"] == "test_001"
        assert mission["ticker"] == "MSFT"
        assert mission["mission_status"] == "planning"
        assert mission["tasks"] == []
        assert mission["version"] == 1

    def test_create_task():
        task = create_ofas_task(
            task_id="data_ingestion",
            name="Data Ingestion",
            responsible=["financial_analyst"],
            consulted=["market_researcher"],
            dependencies=[],
        )
        assert task["id"] == "data_ingestion"
        assert task["status"] == "pending"
        assert task["raci"]["R"] == ["financial_analyst"]
        assert task["raci"]["C"] == ["market_researcher"]
        assert task["raci"]["A"] == ["ofas_supervisor"]
        assert task["retry_count"] == 0

    def test_create_issue():
        issue = create_ofas_issue(
            msg="Balance sheet does not balance",
            owner="dcf_lbo_architect",
            severity="error",
            task_id="model_build",
        )
        assert issue["severity"] == "error"
        assert issue["owner"] == "dcf_lbo_architect"
        assert "timestamp" in issue

    def test_get_ready_tasks():
        mission = create_ofas_mission("t1", "MSFT", "Test")
        t1 = create_ofas_task("data", "Data", ["fa"], dependencies=[])
        t2 = create_ofas_task("model", "Model", ["arch"], dependencies=["data"])
        t3 = create_ofas_task("comps", "Comps", ["val"], dependencies=["data"])
        mission["tasks"] = [t1, t2, t3]

        # Initially only data_ingestion should be ready
        ready = get_ready_tasks(mission)
        assert len(ready) == 1
        assert ready[0]["id"] == "data"

        # After data is done, model and comps should be ready
        t1["status"] = "done"
        ready = get_ready_tasks(mission)
        assert len(ready) == 2
        ready_ids = {t["id"] for t in ready}
        assert "model" in ready_ids
        assert "comps" in ready_ids

    def test_has_blocking_issues():
        mission = create_ofas_mission("t1", "MSFT", "Test")
        t1 = create_ofas_task("data", "Data", ["fa"])
        t1["issues"] = [create_ofas_issue("Warning", "fa", "warn", "data")]
        mission["tasks"] = [t1]
        assert not has_blocking_issues(mission)  # Warns don't block

        t1["issues"].append(create_ofas_issue("BS mismatch", "arch", "error", "data"))
        assert has_blocking_issues(mission)  # Errors block

    test("Create OFAS mission", test_create_mission)
    test("Create OFAS task with RACI", test_create_task)
    test("Create OFAS issue", test_create_issue)
    test("Get ready tasks (dependency graph)", test_get_ready_tasks)
    test("Has blocking issues (severity check)", test_has_blocking_issues)

except Exception as e:
    print(f"  ⚠️ Import failed: {e}")
    failed += 1

# ============================================================
# Test 2: OFAS Supervisor Agent
# ============================================================
print("\n🎯 OFAS Supervisor Agent — Mission Control")
print("=" * 55)

try:
    from app.agents.ofas_supervisor import OFASSupervisorAgent, DEAL_TYPE_TEMPLATES

    def test_supervisor_plan_standard():
        sup = OFASSupervisorAgent()
        result = asyncio.run(
            sup.run(
                task="Evaluate acquisition of TargetCo for $500M",
                context={
                    "action": "plan_mission",
                    "ticker": "MSFT",
                    "deal_type": "standard_corporate",
                },
            )
        )
        assert result.success, f"Planning failed: {result.reasoning}"
        assert result.data["task_count"] == 6
        assert "data_ingestion" in result.data["ready_tasks"]
        # The first ready task should be data_ingestion (no deps)
        mission = result.data["mission"]
        assert mission["mission_status"] == "in_progress"
        assert len(mission["tasks"]) == 6

    def test_supervisor_plan_ma():
        sup = OFASSupervisorAgent()
        result = asyncio.run(
            sup.run(
                task="M&A analysis of AcquirerCo buying TargetCo",
                context={
                    "action": "plan_mission",
                    "ticker": "AAPL",
                    "deal_type": "ma_acquisition",
                },
            )
        )
        assert result.success
        assert (
            "ma_acquisition" in result.reasoning
            or result.data["deal_type"] == "ma_acquisition"
        )

    def test_supervisor_plan_pe_lbo():
        sup = OFASSupervisorAgent()
        result = asyncio.run(
            sup.run(
                task="LBO analysis of TargetCo",
                context={
                    "action": "plan_mission",
                    "ticker": "NFLX",
                    "deal_type": "pe_lbo",
                },
            )
        )
        assert result.success
        assert result.data["task_count"] == 6

    def test_supervisor_status():
        sup = OFASSupervisorAgent()
        plan = asyncio.run(
            sup.run(
                task="Test",
                context={
                    "action": "plan_mission",
                    "ticker": "MSFT",
                    "deal_type": "standard_corporate",
                },
            )
        )
        mission = plan.data["mission"]

        status = asyncio.run(
            sup.run(
                task="status",
                context={"action": "get_status", "mission": mission},
            )
        )
        assert status.success
        assert status.data["total_tasks"] == 6
        assert status.data["completed_tasks"] == 0

    def test_supervisor_quality_gate():
        sup = OFASSupervisorAgent()
        plan = asyncio.run(
            sup.run(
                task="Test",
                context={
                    "action": "plan_mission",
                    "ticker": "MSFT",
                    "deal_type": "standard_corporate",
                },
            )
        )
        mission = plan.data["mission"]

        # Mark model_build as done with valid outputs
        for task in mission["tasks"]:
            if task["id"] == "model_build":
                task["status"] = "done"
                task["outputs"] = {
                    "model_path": "MSFT_3statement_dcf_v1.xlsx",
                    "summary": {"revenue": 100000},
                    "checks": {
                        "balance_sheet_balanced": True,
                        "cash_reconciles": True,
                    },
                }

        gate = asyncio.run(
            sup.run(
                task="quality_gate",
                context={
                    "action": "quality_gate",
                    "mission": mission,
                    "task_id": "model_build",
                },
            )
        )
        assert gate.success
        assert gate.data["passed"]

    def test_templates_exist():
        assert len(DEAL_TYPE_TEMPLATES) >= 3
        assert "standard_corporate" in DEAL_TYPE_TEMPLATES
        assert "ma_acquisition" in DEAL_TYPE_TEMPLATES
        assert "pe_lbo" in DEAL_TYPE_TEMPLATES

    test("Plan standard corporate mission", test_supervisor_plan_standard)
    test("Plan M&A acquisition mission", test_supervisor_plan_ma)
    test("Plan PE/LBO mission", test_supervisor_plan_pe_lbo)
    test("Get mission status", test_supervisor_status)
    test("Quality gate (model_build)", test_supervisor_quality_gate)
    test("Deal type templates exist", test_templates_exist)

except Exception as e:
    print(f"  ⚠️ Import failed: {e}")
    failed += 1

# ============================================================
# Test 3: Excel Model Engine — Formula Preservation
# ============================================================
print("\n📊 Excel Model Engine — Formula Preservation")
print("=" * 55)

try:
    from app.core.tools.excel_model_engine import (
        ExcelModelPopulateTool,
        ExcelExportTablesTool,
        _is_formula_cell,
        TEMPLATE_MAP,
    )

    def test_formula_detection():
        """Test formula cell detection utility"""

        class MockCell:
            def __init__(self, value):
                self.value = value

        assert _is_formula_cell(MockCell("=SUM(A1:A10)")) == True
        assert _is_formula_cell(MockCell("=B7*(1+B8)")) == True
        assert _is_formula_cell(MockCell(100000)) == False
        assert _is_formula_cell(MockCell("Revenue")) == False
        assert _is_formula_cell(MockCell(None)) == False

    def test_template_map_exists():
        assert len(TEMPLATE_MAP) >= 10
        assert "3statement" in TEMPLATE_MAP
        assert "dcf" in TEMPLATE_MAP
        assert "sensitivity" in TEMPLATE_MAP
        assert "football_field" in TEMPLATE_MAP

    def test_populate_tool_schema():
        tool = ExcelModelPopulateTool()
        schema = tool.get_parameters_schema()
        assert "template_id" in schema["properties"]
        assert "ticker" in schema["properties"]
        assert "cell_mappings" in schema["properties"]

    def test_export_tool_schema():
        tool = ExcelExportTablesTool()
        schema = tool.get_parameters_schema()
        assert "model_path" in schema["properties"]
        assert "exports" in schema["properties"]

    test("Formula cell detection", test_formula_detection)
    test("Template map completeness", test_template_map_exists)
    test("Populate tool parameter schema", test_populate_tool_schema)
    test("Export tool parameter schema", test_export_tool_schema)

except Exception as e:
    print(f"  ⚠️ Import failed: {e}")
    failed += 1

# ============================================================
# Test 4: Financial Data API
# ============================================================
print("\n💰 Financial Data API — SEC EDGAR + Yahoo Finance")
print("=" * 55)

try:
    from app.core.tools.financial_data_api import (
        FetchFinancialStatementsTool,
        XBRL_INCOME_STATEMENT,
        XBRL_BALANCE_SHEET,
        XBRL_CASH_FLOW,
    )

    def test_xbrl_mappings():
        assert "revenue" in XBRL_INCOME_STATEMENT.values()
        assert "net_income" in XBRL_INCOME_STATEMENT.values()
        assert "total_assets" in XBRL_BALANCE_SHEET.values()
        assert "cfo" in XBRL_CASH_FLOW.values()

    def test_financial_tool_schema():
        tool = FetchFinancialStatementsTool()
        schema = tool.get_parameters_schema()
        assert "ticker" in schema["properties"]
        assert "statements" in schema["properties"]
        assert "periods" in schema["properties"]

    def test_financial_tool_missing_ticker():
        tool = FetchFinancialStatementsTool()
        result = tool.execute(ticker="")
        assert not result.success
        assert "required" in result.error.lower()

    test("XBRL field mappings", test_xbrl_mappings)
    test("Financial tool parameter schema", test_financial_tool_schema)
    test("Missing ticker returns error", test_financial_tool_missing_ticker)

except Exception as e:
    print(f"  ⚠️ Import failed: {e}")
    failed += 1

# ============================================================
# Test 5: Integration — Existing imports still work
# ============================================================
print("\n🔗 Integration — No Regression on Existing Imports")
print("=" * 55)

try:

    def test_existing_state_imports():
        from app.orchestrator.state import (
            DealState,
            DealStage,
            AgentState,
            WorkflowConfig,
            create_initial_state,
            update_state,
        )

        state = create_initial_state("test", "Test Deal")
        assert state["deal_id"] == "test"
        assert state["current_stage"] == DealStage.INIT

    def test_existing_agent_imports():
        from app.agents import (
            FinancialAnalystAgent,
            ValuationAgent,
            RiskAssessorAgent,
            DCFLBOArchitectAgent,
            OFASSupervisorAgent,
        )

    def test_tool_router_import():
        from app.core.tools.tool_router import ToolRouter, AGENT_TOOL_MAP

        assert "ofas_supervisor" in AGENT_TOOL_MAP
        # Original agents still mapped
        assert "financial_analyst" in AGENT_TOOL_MAP
        assert "dcf_lbo_architect" in AGENT_TOOL_MAP

    test("Existing DealState imports", test_existing_state_imports)
    test("Existing agent imports + OFAS", test_existing_agent_imports)
    test("Tool router with OFAS tools", test_tool_router_import)

except Exception as e:
    print(f"  ⚠️ Import failed: {e}")
    failed += 1

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 55)
print(f"Results: {passed} passed, {failed} failed")
if errors:
    print("\nFailed tests:")
    for name, err in errors:
        print(f"  • {name}: {err}")
print("=" * 55)

sys.exit(0 if failed == 0 else 1)
