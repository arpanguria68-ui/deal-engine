"""
OFAS Phase 4 — Reporting & Compliance Unit Tests
Run with: python test_ofas_phase4.py
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
# Test 1: IC Memo Tool
# ============================================================
print("\nIC Memo Tool")
print("=" * 55)

try:
    from app.core.tools.reporting_tools import GenerateICMemoTool

    def test_memo_schema():
        tool = GenerateICMemoTool()
        schema = tool.get_parameters_schema()
        assert "ticker" in schema["properties"]
        assert "sections" in schema["properties"]
        assert "citations" in schema["properties"]

    def test_memo_generation():
        tool = GenerateICMemoTool()
        result = tool.execute(
            ticker="MSFT",
            deal_name="Microsoft Acquisition Analysis",
            sections={
                "executive_summary": "Microsoft is a compelling acquisition target with strong recurring revenue.",
                "investment_thesis": "Cloud growth at 30% CAGR, margin expansion potential.",
                "financial_analysis": "Revenue $200B, EBITDA margin 45%, FCF yield 3.5%.",
                "valuation": "DCF range $350-$450/share, comps suggest $380-$420.",
                "risks": "Regulatory scrutiny, cloud commoditization, key person risk.",
                "recommendation": "STRONG BUY at current levels. Recommend PROCEED.",
            },
            citations=[
                {
                    "id": "C1",
                    "source": "10-K FY2025",
                    "chunk_id": "chunk_001",
                    "content": "Revenue grew 15% YoY",
                },
                {
                    "id": "C2",
                    "source": "CIM p.12",
                    "chunk_id": "chunk_002",
                    "content": "Cloud segment margin 52%",
                },
                {
                    "id": "C3",
                    "source": "Industry Report",
                    "chunk_id": "chunk_003",
                    "content": "TAM $800B by 2028",
                },
            ],
        )
        assert result.success, result.error
        data = result.data
        assert "memo_path" in data or "format" in data
        if data.get("sections_included"):
            assert "executive_summary" in data["sections_included"]
            assert data["citation_count"] == 3

    def test_memo_no_sections():
        tool = GenerateICMemoTool()
        result = tool.execute(ticker="X", deal_name="Test", sections={})
        assert not result.success

    test("IC memo parameter schema", test_memo_schema)
    test("IC memo generation (PDF or markdown)", test_memo_generation)
    test("IC memo with no sections", test_memo_no_sections)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 2: Deal Deck Tool
# ============================================================
print("\nDeal Deck Tool")
print("=" * 55)

try:
    from app.core.tools.reporting_tools import GenerateDealDeckTool

    def test_deck_schema():
        tool = GenerateDealDeckTool()
        schema = tool.get_parameters_schema()
        assert "ticker" in schema["properties"]
        assert "deal_name" in schema["properties"]

    test("Deal deck parameter schema", test_deck_schema)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 3: ComplianceQA Agent — Memo Validation
# ============================================================
print("\nComplianceQA Agent — Memo Validation")
print("=" * 55)

try:
    from app.agents.compliance_qa_agent import ComplianceQAAgent

    def test_qa_complete_memo():
        agent = ComplianceQAAgent.__new__(ComplianceQAAgent)
        from datetime import datetime

        result = agent._validate_memo(
            {
                "sections": {
                    "executive_summary": "Strong acquisition target with 30% CAGR.",
                    "investment_thesis": "Cloud leadership and margin expansion drive value.",
                    "financial_analysis": "Revenue $200B, EBITDA $90B, FCF $70B.",
                    "valuation": "DCF implies $400/share mid-case.",
                    "risks": "Regulatory, competition, macro. CONFIDENTIAL.",
                    "recommendation": "STRONG BUY — recommend PROCEED at $380/share.",
                },
                "citations": [
                    {"id": "C1", "source": "10-K", "chunk_id": "c1"},
                    {"id": "C2", "source": "CIM", "chunk_id": "c2"},
                    {"id": "C3", "source": "Report", "chunk_id": "c3"},
                ],
            },
            datetime.utcnow(),
        )
        assert result.success
        assert result.data["passed"], f"Expected pass but got: {result.data}"
        assert result.data["issue_count"] == 0

    def test_qa_missing_sections():
        agent = ComplianceQAAgent.__new__(ComplianceQAAgent)
        from datetime import datetime

        result = agent._validate_memo(
            {
                "sections": {
                    "executive_summary": "Brief summary.",
                },
                "citations": [],
            },
            datetime.utcnow(),
        )
        assert result.success
        assert not result.data["passed"]
        assert result.data["issue_count"] >= 5  # 5 missing sections + 0 citations
        missing = result.data["sections_missing"]
        assert "valuation" in missing
        assert "risks" in missing

    def test_qa_insufficient_citations():
        agent = ComplianceQAAgent.__new__(ComplianceQAAgent)
        from datetime import datetime

        result = agent._validate_memo(
            {
                "sections": {
                    "executive_summary": "X" * 100,
                    "investment_thesis": "X" * 100,
                    "financial_analysis": "X" * 100,
                    "valuation": "X" * 100,
                    "risks": "X" * 100,
                    "recommendation": "PROCEED",
                },
                "citations": [{"id": "C1", "source": "test"}],
            },
            datetime.utcnow(),
        )
        assert result.success
        assert not result.data["passed"]
        has_citation_issue = any(
            i["type"] == "insufficient_citations" for i in result.data["issues"]
        )
        assert has_citation_issue

    test("Complete memo passes QA", test_qa_complete_memo)
    test("Missing sections detected", test_qa_missing_sections)
    test("Insufficient citations detected", test_qa_insufficient_citations)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 4: ComplianceQA Agent — Model Validation
# ============================================================
print("\nComplianceQA Agent — Model Validation")
print("=" * 55)

try:
    from app.agents.compliance_qa_agent import ComplianceQAAgent

    def test_qa_model_pass():
        agent = ComplianceQAAgent.__new__(ComplianceQAAgent)
        from datetime import datetime

        result = agent._validate_model(
            {
                "model_outputs": {"summary": {"revenue": 200000}},
                "checks": {
                    "balance_sheet_balanced": True,
                    "cash_reconciles": True,
                    "formula_count": 150,
                },
            },
            datetime.utcnow(),
        )
        assert result.success
        assert result.data["passed"]

    def test_qa_model_bs_fail():
        agent = ComplianceQAAgent.__new__(ComplianceQAAgent)
        from datetime import datetime

        result = agent._validate_model(
            {
                "checks": {"balance_sheet_balanced": False, "cash_reconciles": True},
            },
            datetime.utcnow(),
        )
        assert result.success
        assert not result.data["passed"]
        assert any(i["type"] == "bs_imbalance" for i in result.data["issues"])

    test("Valid model passes QA", test_qa_model_pass)
    test("BS imbalance detected", test_qa_model_bs_fail)

except Exception as e:
    print(f"  Import failed: {e}")
    failed += 1

# ============================================================
# Test 5: Tool Registration
# ============================================================
print("\nTool Registration")
print("=" * 55)

try:
    from app.core.tools.tool_router import AGENT_TOOL_MAP

    def test_memo_agent_tools():
        allowed = AGENT_TOOL_MAP.get("investment_memo_agent", [])
        assert "generate_ic_memo" in allowed
        assert "generate_deal_deck" in allowed

    def test_compliance_agent_registered():
        from app.agents import ComplianceQAAgent

        assert ComplianceQAAgent.name == "compliance_qa_agent"

    def test_compliance_in_tool_map():
        assert "compliance_qa_agent" in AGENT_TOOL_MAP

    test("Memo agent has IC memo + deck tools", test_memo_agent_tools)
    test("ComplianceQAAgent registered", test_compliance_agent_registered)
    test("Compliance agent in AGENT_TOOL_MAP", test_compliance_in_tool_map)

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
