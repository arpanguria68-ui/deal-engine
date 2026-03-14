"""
OFAS Performance Evaluation — Local Qwen (LM Studio)
End-to-End Real-World Scenario Test

Scenario: Apple (AAPL) acquiring a mock AI company 'NeuralBase'
"""

import asyncio
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Any

# Ensure backend is in path
sys.path.insert(0, r"F:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend")

from app.agents.ofas_supervisor import OFASSupervisorAgent
from app.agents.financial_analyst import FinancialAnalystAgent, ValuationAgent
from app.agents.due_diligence_agent import CommercialDueDiligenceAgent
from app.agents.investment_memo_agent import InvestmentMemoAgent
from app.agents.compliance_qa_agent import ComplianceQAAgent
from app.orchestrator.ofas_engine import OFASExecutionEngine
from app.core.tools.financial_data_api import FetchFinancialStatementsTool
from app.core.tools.valuation_tools import (
    FetchComparableCompaniesTool,
    GenerateFootballFieldTool,
)
from app.core.tools.reporting_tools import GenerateICMemoTool

# Mock Registry for Agents
AGENT_REGISTRY = {
    "ofas_supervisor": OFASSupervisorAgent(),
    "financial_analyst": FinancialAnalystAgent(),
    "valuation_agent": ValuationAgent(),
    "due_diligence_agent": CommercialDueDiligenceAgent(),
    "investment_memo_agent": InvestmentMemoAgent(),
    "compliance_qa_agent": ComplianceQAAgent(),
}


async def run_evaluation():
    print("\n" + "=" * 60)
    print("🚀 OFAS Performance Evaluation — Local Qwen (LM Studio)")
    print("=" * 60)

    start_total = time.time()
    telemetry = []

    def log_step(step_name, duration, status="SUCCESS"):
        print(f"  [ {status} ] {step_name:<30} | {duration:>6.2f}s")
        telemetry.append({"step": step_name, "duration": duration, "status": status})

    try:
        # 1. Mission Planning
        print("\n1. Mission Planning...")
        t_start = time.time()
        supervisor = AGENT_REGISTRY["ofas_supervisor"]
        plan_result = await supervisor.run(
            task="Strategize the acquisition of NeuralBase by Apple",
            context={
                "action": "plan_mission",
                "ticker": "AAPL",
                "deal_type": "ma_acquisition",
                "deal_id": "DEAL-E2E-LOCAL",
                "constraints": [
                    "Keep it high-level for performance test",
                    "Focus on synergies",
                ],
            },
        )
        if not plan_result.success:
            raise Exception(f"Planning failed: {plan_result.reasoning}")

        mission = plan_result.data["mission"]
        log_step("Mission Planning (Supervisor)", time.time() - t_start)
        print(f"   Tasks planned: {len(mission['tasks'])}")

        # 2. Financial Data Fetching
        print("\n2. Data Collection...")
        t_start = time.time()
        data_tool = FetchFinancialStatementsTool()
        financial_data = data_tool.execute(ticker="AAPL", periods=3)
        mission["financial_data"] = financial_data.data
        log_step("Financial Data Fetch (Internal)", time.time() - t_start)

        # 3. Parallel Execution Logic (Simplified for script)
        # We'll execute key tasks sequentially for clearer timing logs
        print("\n3. Core Analysis & Deliverables...")

        # 3.1 Due Diligence
        t_start = time.time()
        dd_agent = AGENT_REGISTRY["due_diligence_agent"]
        dd_result = await dd_agent.run(
            task="Evaluate business model of NeuralBase AI",
            context={
                "deal_id": "DEAL-E2E-LOCAL",
                "acquirer": "Apple",
                "target": "NeuralBase AI",
            },
        )
        log_step("Commercial DD (RAG + Synergy)", time.time() - t_start)

        # 3.2 Valuation (Comps)
        t_start = time.time()
        val_agent = AGENT_REGISTRY["valuation_agent"]
        val_result = await val_agent.run(
            task="Perform trading multiples for NeuralBase peers",
            context={"ticker": "AAPL", "deal_id": "DEAL-E2E-LOCAL"},
        )
        log_step("Valuation / Comps Analysis", time.time() - t_start)

        # 3.3 Draft IC Memo
        t_start = time.time()
        memo_agent = AGENT_REGISTRY["investment_memo_agent"]
        memo_result = await memo_agent.run(
            task="Draft an Investment Committee memo for Apple + NeuralBase",
            context={
                "deal_id": "DEAL-E2E-LOCAL",
                "agent_results": [
                    {"agent": "due_diligence_agent", "data": dd_result.data},
                    {"agent": "valuation_agent", "data": val_result.data},
                ],
                "ticker": "AAPL",
            },
        )
        log_step("Investment Memo Drafting", time.time() - t_start)

        # 4. Final Reporting (Tools)
        print("\n4. Final Deliverables (PDF/PPTX)...")
        t_start = time.time()
        memo_tool = GenerateICMemoTool()

        # Extract sections for the tool
        sections = memo_result.data.get("sections_dict", {})
        if not sections and "memo" in memo_result.data:
            # Simple fallback if extraction didn't work as expected
            sections = {"executive_summary": memo_result.data["memo"][:5000]}

        final_pdf = memo_tool.execute(
            ticker="AAPL",
            deal_name="Apple x NeuralBase",
            sections=sections,
            citations=[
                {
                    "id": "C1",
                    "source": "Internal Deal Memo",
                    "chunk_id": "ch_1",
                    "content": "Synergy potential high",
                }
            ],
        )
        log_step("IC Memo PDF Generation", time.time() - t_start)

        # 5. Compliance QA
        print("\n5. Compliance QA...")
        t_start = time.time()
        qa_agent = AGENT_REGISTRY["compliance_qa_agent"]
        qa_result = await qa_agent.run(
            task="Validate Apple-NeuralBase deliverables",
            context={
                "action": "validate_memo",
                "sections": sections,
                "citations": [{"id": "C1"}],  # Simulated few citations
            },
        )
        log_step("Compliance QA Audit", time.time() - t_start)

        total_duration = time.time() - start_total
        print("\n" + "=" * 60)
        print("📊 EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Total Workflow Time: {total_duration:.2f}s")
        print(f"Model used:          Local Qwen 2.5 (9B) via LM Studio")
        print(f"Context Window:      12,000 tokens")
        print(f"Deliverables generated: {final_pdf.data.get('memo_path', 'FAILED')}")
        print(
            f"QA Status:           {'PASS' if qa_result.data.get('passed') else 'FAIL'}"
        )

        # Save results to a report
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "llm": "qwen2.5-9b-local",
            "total_duration_s": total_duration,
            "steps": telemetry,
            "qa_passed": qa_result.data.get("passed", False),
        }

        with open("ofas_performance_report.json", "w") as f:
            json.dump(report, f, indent=4)
        print(f"\nDetailed report saved to: ofas_performance_report.json")

    except Exception as e:
        print(f"\n❌ EVALUATION FAILED: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_evaluation())
