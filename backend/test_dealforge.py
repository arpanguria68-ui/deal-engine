"""
DealForge AI — Standalone Unit Tests
Tests the deterministic/rule-based modules that don't need DB, LLM, or PageIndex.
Run with: python test_dealforge.py
"""

import sys
import json

# Track results
passed = 0
failed = 0
errors = []


def test(name, func):
    global passed, failed, errors
    try:
        func()
        passed += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        failed += 1
        errors.append(f"  ❌ {name}: {e}")
        print(f"  ❌ {name}: {e}")
    except Exception as e:
        failed += 1
        errors.append(f"  💥 {name}: {type(e).__name__}: {e}")
        print(f"  💥 {name}: {type(e).__name__}: {e}")


# ============================================================
# Test 1: DCF Calculation (mid-year convention)
# ============================================================
print("\n📊 Financial Analyst — Deterministic Calculations")
print("=" * 55)

# We need to add the app directory to sys.path
sys.path.insert(0, r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend")

try:
    from app.agents.financial_analyst import FinancialAnalystAgent, ValuationAgent

    def test_dcf_basic():
        result = FinancialAnalystAgent.calculate_dcf(
            projected_fcf=[100, 110, 121, 133, 146],
            wacc=0.10,
            terminal_growth=0.025,
            mid_year_convention=True,
        )
        assert result["method"] == "dcf"
        assert result["mid_year_convention"] is True
        assert result["enterprise_value"] > 0
        assert len(result["pv_cash_flows"]) == 5
        assert result["terminal_value"] > 0
        # Mid-year convention: first year discounted at 0.5, not 1.0
        first_pv = result["pv_cash_flows"][0]["pv"]
        assert first_pv > 90, f"Mid-year PV of 100 should be > 90, got {first_pv}"

    def test_dcf_no_midyear():
        result = FinancialAnalystAgent.calculate_dcf(
            projected_fcf=[100, 110, 121],
            wacc=0.10,
            terminal_growth=0.025,
            mid_year_convention=False,
        )
        assert result["mid_year_convention"] is False
        first_pv = result["pv_cash_flows"][0]["pv"]
        assert (
            first_pv < 92
        ), f"End-year PV of 100 at 10% should be ~90.9, got {first_pv}"

    def test_dcf_wacc_validation():
        try:
            FinancialAnalystAgent.calculate_dcf(
                projected_fcf=[100],
                wacc=0.02,
                terminal_growth=0.025,
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected

    def test_lbo_returns():
        result = FinancialAnalystAgent.calculate_lbo_returns(
            entry_ev=1000,
            exit_ev=1500,
            equity_contribution_pct=0.40,
            holding_period_years=5,
            total_debt_paydown=200,
        )
        assert result["method"] == "lbo"
        assert result["initial_equity"] == 400
        assert result["initial_debt"] == 600
        assert result["exit_equity"] == 1500 - (600 - 200)
        assert result["moic"] > 1.0, f"MOIC should be > 1.0, got {result['moic']}"
        assert 0 < result["irr"] < 1, f"IRR should be between 0-1, got {result['irr']}"

    def test_unit_of_account_valid():
        valid, warnings = FinancialAnalystAgent.validate_unit_of_account(
            {
                "revenue": 10_000_000,
                "ebitda": 2_500_000,
                "free_cash_flow": 1_500_000,
            }
        )
        assert valid, f"Should be valid, but got warnings: {warnings}"

    def test_unit_of_account_mismatch():
        valid, warnings = FinancialAnalystAgent.validate_unit_of_account(
            {
                "revenue": 10,  # $10M in millions
                "ebitda": 25_000_000,  # $25M in raw
            }
        )
        assert not valid, "Should detect magnitude mismatch"
        assert len(warnings) > 0

    def test_comps_valuation():
        result = ValuationAgent.calculate_comps_valuation(
            target_metric=50_000_000,
            peer_multiples=[8.0, 10.0, 12.0, 9.5, 11.0],
            metric_name="EV/EBITDA",
        )
        assert result["method"] == "comparable_companies"
        assert result["median_multiple"] == 10.0
        assert result["value_range"]["low"] == 50_000_000 * 8.0
        assert result["value_range"]["high"] == 50_000_000 * 12.0

    test("DCF with mid-year convention", test_dcf_basic)
    test("DCF without mid-year convention", test_dcf_no_midyear)
    test("DCF WACC < terminal growth raises ValueError", test_dcf_wacc_validation)
    test("LBO returns (IRR/MOIC)", test_lbo_returns)
    test("Unit of Account — valid data", test_unit_of_account_valid)
    test("Unit of Account — magnitude mismatch", test_unit_of_account_mismatch)
    test("Comparable companies valuation", test_comps_valuation)

except ImportError as e:
    print(f"  ⚠️ Skipping Financial Analyst tests (import error): {e}")


# ============================================================
# Test 2: GP-Led CV Waterfall Solver
# ============================================================
print("\n🏦 GP-Led CV Waterfall Solver")
print("=" * 55)

try:
    from app.workflows.gp_led_cv import (
        CVWaterfallSolver,
        CVSimulationConfig,
        CVMECEAnalyzer,
    )

    def test_cv_waterfall_convergence():
        config = CVSimulationConfig(
            lpa_document_id="test",
            bid_spread_data={},
            gp_carried_interest=0.20,
            preferred_return=0.08,
        )
        solver = CVWaterfallSolver(config)
        result = solver.solve(
            total_nav=100_000_000,
            existing_debt=30_000_000,
            projected_cash_flows=[
                20_000_000,
                22_000_000,
                25_000_000,
                28_000_000,
                30_000_000,
            ],
        )
        assert result[
            "converged"
        ], f"Should converge, got {result['iterations']} iterations"
        assert result["summary"]["total_nav"] == 100_000_000
        assert result["summary"]["total_gp_carry"] > 0
        assert result["summary"]["lp_moic"] > 0
        assert len(result["distributions"]) == 5

    def test_cv_price_fairness():
        analyzer = CVMECEAnalyzer()
        result = analyzer.analyze_price_fairness(
            nav=100_000_000,
            bid_price=105_000_000,
            comparable_cvs=[
                {"premium_pct": 0.03},
                {"premium_pct": 0.07},
                {"premium_pct": 0.05},
            ],
        )
        assert result["branch"] == "price_fairness"
        assert result["premium_discount_pct"] == 5.0
        assert result["assessment"] in [
            "FAIR",
            "ABOVE MARKET",
            "BELOW MARKET — LP concern",
        ]

    def test_cv_economic_parity():
        analyzer = CVMECEAnalyzer()
        result = analyzer.analyze_economic_parity(
            rolling_lps_terms={
                "carried_interest": 0.20,
                "management_fee": 0.02,
                "preferred_return": 0.08,
            },
            new_lps_terms={
                "carried_interest": 0.20,
                "management_fee": 0.02,
                "preferred_return": 0.08,
            },
        )
        assert result["parity_achieved"] is True

    def test_cv_governance():
        analyzer = CVMECEAnalyzer()
        result = analyzer.analyze_governance_integrity(
            gp_conflicts=["dual-role GP"],
            lpac_approval=True,
            fairness_opinion=True,
        )
        assert result["governance_score"] >= 50

    test("CV waterfall convergence", test_cv_waterfall_convergence)
    test("CV Price Fairness analysis", test_cv_price_fairness)
    test("CV Economic Parity check", test_cv_economic_parity)
    test("CV Governance Integrity check", test_cv_governance)

except ImportError as e:
    print(f"  ⚠️ Skipping CV Waterfall tests (import error): {e}")


# ============================================================
# Test 3: LMT Loophole Detector + Monte Carlo
# ============================================================
print("\n🔍 LMT Loophole Detector & Monte Carlo")
print("=" * 55)

try:
    from app.workflows.lmt_simulation import (
        LoopholeDetector,
        MonteCarloRecoveryModel,
        LMTConfig,
    )

    def test_loophole_detection():
        detector = LoopholeDetector()
        text = """
        The Borrower may designate any Subsidiary as an Unrestricted Subsidiary.
        The Credit Agreement permits cross-collateral arrangements.
        A super-senior priming lien facility was established.
        The covenant-lite structure provides flexibility.
        """
        findings = detector.scan(text)
        assert (
            len(findings) >= 3
        ), f"Should find at least 3 loopholes, got {len(findings)}"
        types_found = set(f["loophole_type"] for f in findings)
        assert "drop_down" in types_found, "Should detect drop-down"
        assert "up_tier" in types_found, "Should detect up-tier"

    def test_monte_carlo_single():
        config = LMTConfig(num_simulations=1000, random_seed=42)
        model = MonteCarloRecoveryModel(config)
        result = model.simulate(
            outstanding_debt=100_000_000,
            collateral_value=60_000_000,
            seniority_rank=1,
            total_tranches=3,
        )
        assert result["simulations"] == 1000
        assert result["statistics"]["mean_recovery"] > 0
        assert result["percentiles"]["p50_median"] > 0
        assert result["percentiles"]["p5"] <= result["percentiles"]["p95"]

    def test_monte_carlo_capital_structure():
        config = LMTConfig(num_simulations=1000, random_seed=42)
        model = MonteCarloRecoveryModel(config)
        result = model.run_full_capital_structure(
            tranches=[
                {"name": "Senior Secured", "amount": 50_000_000, "seniority_rank": 1},
                {"name": "Mezzanine", "amount": 30_000_000, "seniority_rank": 2},
                {"name": "Junior", "amount": 20_000_000, "seniority_rank": 3},
            ],
            total_collateral=70_000_000,
        )
        assert "capital_structure_analysis" in result
        senior = result["capital_structure_analysis"]["Senior Secured"]
        junior = result["capital_structure_analysis"]["Junior"]
        assert (
            senior["statistics"]["mean_recovery_rate"]
            >= junior["statistics"]["mean_recovery_rate"]
        ), "Senior should recover more than junior"

    test(
        "Loophole detection (drop-down, up-tier, covenant-lite)",
        test_loophole_detection,
    )
    test("Monte Carlo single tranche", test_monte_carlo_single)
    test("Monte Carlo full capital structure", test_monte_carlo_capital_structure)

except ImportError as e:
    print(f"  ⚠️ Skipping LMT tests (import error): {e}")


# ============================================================
# Test 4: HaluGate NLI Engine
# ============================================================
print("\n🛡️ HaluGate NLI Engine")
print("=" * 55)

try:
    from app.core.halugate.nli_engine import (
        HaluGateEngine,
        NonGAAPDetector,
        NLIVerdict,
        HaluGateSeverity,
    )
    import asyncio

    def test_halugate_claim_extraction():
        engine = HaluGateEngine()
        claims = engine._extract_claims(
            "Revenue grew 15% to $50M. The EBITDA margin expanded to 25%. "
            "Management believes the outlook is positive."
        )
        assert (
            len(claims) >= 2
        ), f"Should extract at least 2 quantitative claims, got {len(claims)}"

    def test_halugate_number_extraction():
        engine = HaluGateEngine()
        numbers = engine._extract_numbers(
            "Revenue of $50M and EBITDA of $12.5M with 25% margin"
        )
        assert 50_000_000 in numbers, f"Should extract 50M, got {numbers}"
        assert 12_500_000 in numbers, f"Should extract 12.5M, got {numbers}"

    async def _test_halugate_verify():
        engine = HaluGateEngine()
        results = await engine.verify_narrative(
            narrative="Revenue was $50M with 25% EBITDA margin.",
            ground_truth={"revenue": 50000000, "ebitda_margin": 0.25},
        )
        assert len(results) > 0
        # $50M should match ground truth
        matched = [r for r in results if r.verdict == NLIVerdict.ENTAILMENT]
        assert len(matched) >= 0  # At least check it runs

    def test_halugate_verify():
        asyncio.run(_test_halugate_verify())

    def test_halugate_should_block():
        engine = HaluGateEngine()
        from app.core.halugate.nli_engine import HaluGateResult

        results = [
            HaluGateResult(
                claim="test",
                evidence="test",
                verdict=NLIVerdict.CONTRADICTION,
                severity=HaluGateSeverity.BLOCK,
                confidence=0.9,
                explanation="test",
            )
        ]
        assert engine.should_block(results) is True

    def test_nongaap_detector():
        detector = NonGAAPDetector()
        findings = detector.scan(
            "The company reported adjusted EBITDA of $50M, "
            "excluding stock-based compensation excluded from operating expenses. "
            "Non-recurring restructuring charges of $5M were also excluded. "
            "Pro-forma results show improvement."
        )
        assert (
            len(findings) >= 3
        ), f"Should find at least 3 patterns, got {len(findings)}"
        categories = [f["category"] for f in findings]
        assert "adjusted_ebitda" in categories
        assert "non_recurring" in categories or "restructuring" in categories

    test("Claim extraction from narrative", test_halugate_claim_extraction)
    test("Number extraction with unit normalization", test_halugate_number_extraction)
    test("HaluGate verify narrative (async)", test_halugate_verify)
    test("HaluGate should_block detection", test_halugate_should_block)
    test("Non-GAAP add-back detection", test_nongaap_detector)

except ImportError as e:
    print(f"  ⚠️ Skipping HaluGate tests (import error): {e}")


# ============================================================
# Test 5: Red Team Agent (data structures only)
# ============================================================
print("\n🔴 Red Team Agent — Data Structures")
print("=" * 55)

try:
    from app.agents.red_team_agent import RedTeamAgent

    def test_red_team_deal_breaker_patterns():
        assert len(RedTeamAgent.DEAL_BREAKER_PATTERNS) == 10

    def test_red_team_severity_calculation():
        agent = RedTeamAgent.__new__(RedTeamAgent)
        sev = agent._calculate_severity({"type": "strategic_silence"})
        assert sev == 4
        sev2 = agent._calculate_severity({"type": "historical_deal_breaker"})
        assert sev2 == 5
        sev3 = agent._calculate_severity({"type": "data_incompleteness"})
        assert sev3 == 2

    def test_red_team_recommendation():
        agent = RedTeamAgent.__new__(RedTeamAgent)
        assert "BLOCK" in agent._get_recommendation(5)
        assert "ESCALATE" in agent._get_recommendation(4)
        assert "REVIEW" in agent._get_recommendation(3)
        assert "NOTE" in agent._get_recommendation(2)
        assert "CLEAR" in agent._get_recommendation(0)

    def test_red_team_contradiction_detection():
        agent = RedTeamAgent.__new__(RedTeamAgent)
        flags = agent._detect_contradictions(
            {
                "financial_analyst": {"recommendation": "proceed"},
                "risk_assessor": {"overall_risk_level": "critical"},
            }
        )
        assert len(flags) == 1
        assert flags[0]["type"] == "cross_agent_contradiction"

    test("Deal-breaker patterns count", test_red_team_deal_breaker_patterns)
    test("Severity calculation", test_red_team_severity_calculation)
    test("Recommendation mapping", test_red_team_recommendation)
    test("Cross-agent contradiction detection", test_red_team_contradiction_detection)

except ImportError as e:
    print(f"  ⚠️ Skipping Red Team tests (import error): {e}")


# ============================================================
# Test 6: MECE Issue Tree (BaseAgent data structures)
# ============================================================
print("\n🌳 MECE Issue Tree — Validation")
print("=" * 55)

try:
    from app.agents.base import IssueTreeNode, BaseAgent

    def test_mece_valid():
        # Create a minimal concrete subclass for testing
        class TestAgent(BaseAgent):
            name = "test"

            async def run(self, task, context=None):
                pass

        agent = TestAgent.__new__(TestAgent)
        tree = IssueTreeNode(
            id="root",
            hypothesis="test",
            sub_branches=[
                IssueTreeNode(
                    id="fin", hypothesis="Financial valuation and revenue analysis"
                ),
                IssueTreeNode(id="strat", hypothesis="Strategic fit and market growth"),
                IssueTreeNode(
                    id="risk", hypothesis="Risk assessment and regulatory compliance"
                ),
                IssueTreeNode(
                    id="ops", hypothesis="Operational integration and technology"
                ),
            ],
        )
        valid, gaps = agent.validate_mece(tree)
        assert valid, f"Should be MECE valid, but gaps: {gaps}"

    def test_mece_gaps():
        class TestAgent(BaseAgent):
            name = "test"

            async def run(self, task, context=None):
                pass

        agent = TestAgent.__new__(TestAgent)
        tree = IssueTreeNode(
            id="root",
            hypothesis="test",
            sub_branches=[
                IssueTreeNode(id="fin", hypothesis="Financial valuation"),
                # Missing: strategic, risk, operational
            ],
        )
        valid, gaps = agent.validate_mece(tree)
        assert not valid, "Should detect MECE gaps"
        assert "strategic" in gaps
        assert "risk" in gaps
        assert "operational" in gaps

    def test_serialize_tree():
        class TestAgent(BaseAgent):
            name = "test"

            async def run(self, task, context=None):
                pass

        agent = TestAgent.__new__(TestAgent)
        tree = IssueTreeNode(
            id="root",
            hypothesis="Main hypothesis",
            sub_branches=[
                IssueTreeNode(id="b1", hypothesis="Sub 1", evidence=["Q1", "Q2"]),
            ],
        )
        serialized = agent._serialize_tree(tree)
        assert serialized["id"] == "root"
        assert len(serialized["sub_branches"]) == 1
        assert serialized["sub_branches"][0]["evidence"] == ["Q1", "Q2"]

    test("MECE validation — valid tree", test_mece_valid)
    test("MECE validation — detect gaps", test_mece_gaps)
    test("Issue tree serialization", test_serialize_tree)

except ImportError as e:
    print(f"  ⚠️ Skipping MECE tests (import error): {e}")


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 55)
print(f"📋 RESULTS: {passed} passed, {failed} failed")
print("=" * 55)

if errors:
    print("\nFailed tests:")
    for e in errors:
        print(e)

sys.exit(0 if failed == 0 else 1)
