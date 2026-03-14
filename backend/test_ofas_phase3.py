"""
OFAS Phase 3 — RAG Wiring + MemoryEntry + Enhanced DD Tests
Run with: python test_ofas_phase3.py
"""

import sys
import os

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
# Test 1: AgentType Enum Extended
# ============================================================
print("\nAgentType Enum Extension")
print("=" * 55)

try:
    from app.db.models import AgentType

    def test_original_agents():
        assert AgentType.FINANCIAL_ANALYST == "financial_analyst"
        assert AgentType.LEGAL_ADVISOR == "legal_advisor"
        assert AgentType.RISK_ASSESSOR == "risk_assessor"

    def test_new_agents():
        assert AgentType.DUE_DILIGENCE_AGENT == "due_diligence_agent"
        assert AgentType.DCF_LBO_ARCHITECT == "dcf_lbo_architect"
        assert AgentType.OFAS_SUPERVISOR == "ofas_supervisor"
        assert AgentType.VALUATION_AGENT == "valuation_agent"
        assert AgentType.BUSINESS_ANALYST == "business_analyst"

    def test_agent_count():
        agent_values = [a.value for a in AgentType]
        assert len(agent_values) >= 18, f"Expected 18+ agents, got {len(agent_values)}"

    test("Original agents still valid", test_original_agents)
    test("New OFAS agents in enum", test_new_agents)
    test("AgentType has 18+ members", test_agent_count)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 2: MemoryService
# ============================================================
print("\nMemoryService")
print("=" * 55)

try:
    from app.core.memory.memory_service import MemoryService, get_memory_service

    def test_memory_service_singleton():
        svc1 = get_memory_service()
        svc2 = get_memory_service()
        assert svc1 is svc2

    def test_memory_service_init():
        svc = MemoryService()
        assert svc._session_factory is None  # Uses default

    def test_memory_service_custom_session():
        svc = MemoryService(session_factory="fake_factory")
        assert svc._session_factory == "fake_factory"

    test("MemoryService singleton", test_memory_service_singleton)
    test("MemoryService default init", test_memory_service_init)
    test("MemoryService custom session factory", test_memory_service_custom_session)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 3: Enhanced DD Agent Structure
# ============================================================
print("\nEnhanced DD Agent")
print("=" * 55)

try:
    from app.agents.due_diligence_agent import CommercialDueDiligenceAgent

    def test_dd_agent_properties():
        agent = CommercialDueDiligenceAgent.__new__(CommercialDueDiligenceAgent)
        assert agent.name == "due_diligence_agent"
        assert "synergy" in agent.description

    def test_dd_agent_has_synergy():
        assert hasattr(CommercialDueDiligenceAgent, "_run_synergy_analysis")

    def test_dd_agent_has_memory_integration():
        assert hasattr(CommercialDueDiligenceAgent, "_get_cross_deal_context")
        assert hasattr(CommercialDueDiligenceAgent, "_store_findings")

    def test_dd_agent_has_parse():
        assert hasattr(CommercialDueDiligenceAgent, "_parse_output")

    test("DD agent name and description", test_dd_agent_properties)
    test("DD agent has synergy analysis", test_dd_agent_has_synergy)
    test("DD agent has memory integration", test_dd_agent_has_memory_integration)
    test("DD agent has output parser", test_dd_agent_has_parse)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 4: BaseAgent RAG Methods (already wired)
# ============================================================
print("\nBaseAgent RAG Methods")
print("=" * 55)

try:
    from app.agents.base import BaseAgent

    def test_base_has_retrieve_context():
        assert hasattr(BaseAgent, "retrieve_context")

    def test_base_has_store_to_memory():
        assert hasattr(BaseAgent, "store_to_memory")

    def test_base_has_run_with_structure():
        assert hasattr(BaseAgent, "run_with_structure")

    test("BaseAgent.retrieve_context exists", test_base_has_retrieve_context)
    test("BaseAgent.store_to_memory exists", test_base_has_store_to_memory)
    test("BaseAgent.run_with_structure exists", test_base_has_run_with_structure)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 5: Integration — All Imports Still Work
# ============================================================
print("\nIntegration")
print("=" * 55)

try:

    def test_all_agents_import():
        from app.agents import (
            FinancialAnalystAgent,
            ValuationAgent,
            RiskAssessorAgent,
            DCFLBOArchitectAgent,
            OFASSupervisorAgent,
        )
        from app.agents.due_diligence_agent import CommercialDueDiligenceAgent

    def test_memory_service_import():
        from app.core.memory.memory_service import MemoryService, get_memory_service

    def test_state_import():
        from app.orchestrator.state import (
            OFASTask,
            OFASMissionState,
            create_ofas_mission,
        )

    test("All agent imports work", test_all_agents_import)
    test("MemoryService imports work", test_memory_service_import)
    test("OFAS state imports work", test_state_import)

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
