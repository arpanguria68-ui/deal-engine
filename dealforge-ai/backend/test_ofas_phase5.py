"""
OFAS Phase 5 — Optimization & Production Readiness Tests
Run with: python test_ofas_phase5.py
"""

import sys
import asyncio

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
# Test 1: Execution Engine — Parallel Scheduling
# ============================================================
print("\nExecution Engine — Parallel Scheduling")
print("=" * 55)

try:
    from app.orchestrator.ofas_engine import OFASExecutionEngine
    from app.orchestrator.state import create_ofas_mission, create_ofas_task

    def test_engine_init():
        engine = OFASExecutionEngine(
            agent_timeout_seconds=60,
            max_parallel=4,
        )
        assert engine.agent_timeout == 60
        assert engine.max_parallel == 4

    def test_ready_tasks_detection():
        from app.orchestrator.state import get_ready_tasks

        mission = create_ofas_mission("d1", "MSFT", "Analyze MSFT")
        t1 = create_ofas_task("t1", "Data Collection", ["financial_analyst"])
        t2 = create_ofas_task(
            "t2", "Valuation", ["valuation_agent"], dependencies=["t1"]
        )
        t3 = create_ofas_task("t3", "Legal Review", ["legal_advisor"])

        mission["tasks"] = [t1, t2, t3]

        # t1 and t3 should be ready (no dependencies)
        ready = get_ready_tasks(mission)
        assert len(ready) == 2
        ready_ids = {t["id"] for t in ready}
        assert "t1" in ready_ids
        assert "t3" in ready_ids
        assert "t2" not in ready_ids  # depends on t1

    def test_ready_tasks_after_completion():
        from app.orchestrator.state import get_ready_tasks

        mission = create_ofas_mission("d2", "AAPL", "Analyze")
        t1 = create_ofas_task("t1", "Data", ["financial_analyst"])
        t1["status"] = "done"
        t2 = create_ofas_task(
            "t2", "Valuation", ["valuation_agent"], dependencies=["t1"]
        )

        mission["tasks"] = [t1, t2]

        ready = get_ready_tasks(mission)
        assert len(ready) == 1
        assert ready[0]["id"] == "t2"

    def test_max_parallel_limit():
        engine = OFASExecutionEngine(max_parallel=2)
        mission = create_ofas_mission("d3", "X", "Test")
        for i in range(5):
            mission["tasks"].append(
                create_ofas_task(f"t{i}", f"Task {i}", ["financial_analyst"])
            )
        # Engine should limit batch to 2
        from app.orchestrator.state import get_ready_tasks

        ready = get_ready_tasks(mission)
        batch = ready[: engine.max_parallel]
        assert len(batch) == 2

    test("Engine initialization", test_engine_init)
    test("Ready tasks detection (no deps)", test_ready_tasks_detection)
    test("Ready tasks after dependency completes", test_ready_tasks_after_completion)
    test("Max parallel batch limit", test_max_parallel_limit)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 2: Review Gates
# ============================================================
print("\nReview Gates")
print("=" * 55)

try:
    from app.orchestrator.ofas_engine import (
        OFASExecutionEngine,
        ReviewGateType,
        DEFAULT_REVIEW_GATES,
    )
    from app.orchestrator.state import create_ofas_mission

    def test_auto_gate_pass():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d4", "MSFT", "Test")
        mission["financial_data"] = {"income": {}}
        mission["rag_index_path"] = "/path/to/index"

        result = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_review_gate("after_data_collection", mission)
        )
        assert result.passed
        assert result.checks["financial_data_complete"]
        assert result.checks["rag_index_populated"]

    def test_auto_gate_fail():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d5", "X", "Test")
        # No financial data

        result = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_review_gate("after_data_collection", mission)
        )
        assert not result.passed

    def test_human_gate_blocks():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d6", "Y", "Test")

        result = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_review_gate("after_model_build", mission)
        )
        assert not result.passed
        assert result.requires_human

    def test_human_gate_approved():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d7", "Z", "Test")

        result = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_review_gate(
                "after_model_build", mission, human_decision=True
            )
        )
        assert result.passed
        assert result.human_approved

    def test_unknown_gate_passes():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d8", "X", "Test")

        result = asyncio.get_event_loop().run_until_complete(
            engine.evaluate_review_gate("nonexistent_gate", mission)
        )
        assert result.passed

    def test_default_gates_count():
        assert len(DEFAULT_REVIEW_GATES) == 4

    test("Auto gate passes with data", test_auto_gate_pass)
    test("Auto gate fails without data", test_auto_gate_fail)
    test("Human gate blocks without approval", test_human_gate_blocks)
    test("Human gate passes with approval", test_human_gate_approved)
    test("Unknown gate auto-passes", test_unknown_gate_passes)
    test("4 default review gates configured", test_default_gates_count)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 3: Mission Monitoring
# ============================================================
print("\nMission Monitoring")
print("=" * 55)

try:
    from app.orchestrator.ofas_engine import OFASExecutionEngine
    from app.orchestrator.state import create_ofas_mission, create_ofas_task

    def test_monitor_healthy():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d9", "MSFT", "Test")
        t1 = create_ofas_task("t1", "Task 1", ["fa"])
        t1["status"] = "done"
        t2 = create_ofas_task("t2", "Task 2", ["va"])
        mission["tasks"] = [t1, t2]

        monitor = engine.mission_monitor(mission)
        assert monitor["progress_pct"] == 50.0
        assert monitor["health"] == "healthy"
        assert monitor["tasks"]["done"] == 1
        assert monitor["tasks"]["pending"] == 1

    def test_monitor_degraded():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d10", "X", "Test")
        t1 = create_ofas_task("t1", "Blocked Task", ["fa"])
        t1["status"] = "blocked"
        t1["issues"].append(
            {
                "msg": "timeout",
                "severity": "warn",
                "owner": "fa",
                "task_id": "t1",
                "timestamp": "",
            }
        )
        mission["tasks"] = [t1]

        monitor = engine.mission_monitor(mission)
        assert monitor["health"] == "degraded"

    def test_monitor_critical():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d11", "X", "Test")
        t1 = create_ofas_task("t1", "Error Task", ["fa"])
        t1["issues"].append(
            {
                "msg": "crash",
                "severity": "error",
                "owner": "fa",
                "task_id": "t1",
                "timestamp": "",
            }
        )
        mission["tasks"] = [t1]

        monitor = engine.mission_monitor(mission)
        assert monitor["health"] == "critical"

    test("Monitor shows 50% progress (1/2 done)", test_monitor_healthy)
    test("Monitor shows degraded health (blocked)", test_monitor_degraded)
    test("Monitor shows critical health (errors)", test_monitor_critical)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 4: Error Recovery
# ============================================================
print("\nError Recovery")
print("=" * 55)

try:
    from app.orchestrator.ofas_engine import OFASExecutionEngine
    from app.orchestrator.state import create_ofas_mission, create_ofas_task

    def test_recovery_resets_blocked():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d12", "X", "Test")
        t1 = create_ofas_task("t1", "Blocked Task", ["fa"])
        t1["status"] = "blocked"
        t1["retry_count"] = 0
        t1["issues"].append(
            {
                "msg": "timeout",
                "severity": "error",
                "owner": "fa",
                "task_id": "t1",
                "timestamp": "",
            }
        )
        mission["tasks"] = [t1]

        updated = asyncio.get_event_loop().run_until_complete(
            engine.recover_blocked_tasks(mission, {})
        )
        assert updated["tasks"][0]["status"] == "pending"
        assert updated["tasks"][0]["retry_count"] == 1

    def test_recovery_exceeds_max_retries():
        engine = OFASExecutionEngine()
        mission = create_ofas_mission("d13", "X", "Test")
        t1 = create_ofas_task("t1", "Stuck Task", ["fa"])
        t1["status"] = "blocked"
        t1["retry_count"] = 3
        mission["tasks"] = [t1]

        updated = asyncio.get_event_loop().run_until_complete(
            engine.recover_blocked_tasks(mission, {})
        )
        assert updated["tasks"][0]["status"] == "needs_review"

    test("Recovery resets blocked task to pending", test_recovery_resets_blocked)
    test("Recovery escalates after max retries", test_recovery_exceeds_max_retries)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 5: Telemetry
# ============================================================
print("\nTelemetry")
print("=" * 55)

try:
    from app.orchestrator.ofas_engine import OFASExecutionEngine

    def test_telemetry_recording():
        engine = OFASExecutionEngine()
        engine._record_telemetry("m1", "t1", "done")
        engine._record_telemetry("m1", "t2", "error", "timeout")

        events = engine.get_telemetry("m1")
        assert len(events) == 2
        assert events[0]["status"] == "done"
        assert events[1]["detail"] == "timeout"

    def test_performance_summary():
        engine = OFASExecutionEngine()
        engine._record_telemetry("m2", "t1", "done")
        engine._record_telemetry("m2", "t2", "done")
        engine._record_telemetry("m2", "t3", "error", "fail")

        summary = engine.get_performance_summary("m2")
        assert summary["tasks_completed"] == 2
        assert summary["tasks_failed"] == 1
        assert summary["success_rate"] == 66.7

    test("Telemetry event recording", test_telemetry_recording)
    test("Performance summary calculation", test_performance_summary)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 6: Integration — All Phases Still Import
# ============================================================
print("\nIntegration — All Phases")
print("=" * 55)

try:

    def test_all_imports():
        from app.agents import (
            OFASSupervisorAgent,
            ComplianceQAAgent,
            FinancialAnalystAgent,
            ValuationAgent,
        )
        from app.core.tools.valuation_tools import (
            FetchComparableCompaniesTool,
            GenerateFootballFieldTool,
            RunSensitivityAnalysisTool,
        )
        from app.core.tools.reporting_tools import (
            GenerateICMemoTool,
            GenerateDealDeckTool,
        )
        from app.core.memory.memory_service import MemoryService
        from app.orchestrator.ofas_engine import OFASExecutionEngine

    def test_tool_count():
        from app.core.tools.tool_router import AGENT_TOOL_MAP

        # Should have all OFAS agents
        assert "ofas_supervisor" in AGENT_TOOL_MAP
        assert "valuation_agent" in AGENT_TOOL_MAP
        assert "compliance_qa_agent" in AGENT_TOOL_MAP
        assert "investment_memo_agent" in AGENT_TOOL_MAP

    test("All 5 phases import cleanly", test_all_imports)
    test("All OFAS agents in AGENT_TOOL_MAP", test_tool_count)

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
