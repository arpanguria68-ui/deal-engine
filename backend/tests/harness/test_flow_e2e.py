"""End-to-end runs of agents and the deal workflow on the offline mock provider."""

from app.core.harness.trace import start_trace


async def test_deal_workflow_completes_and_reports_trace(mock_llm):
    from app.orchestrator.graph import get_orchestrator

    orchestrator = get_orchestrator()
    final = await orchestrator.run_deal(
        deal_id="e2e-1",
        deal_name="Deal-Acme",
        context={"target_company": "Acme Corp", "deal_id": "e2e-1"},
    )

    assert final.get("error_message") is None, final.get("error_message")
    assert final["current_stage"] == "completed"
    assert "red_team" in final["stage_history"]
    assert "scoring" in final["stage_history"]

    trace = final["harness_trace"]
    assert trace["llm_calls"] > 0
    assert trace["llm_errors"] == 0
    assert set(trace["providers"]) == {"mock"}
    assert {"financial_analyst", "market_researcher"} <= set(trace["per_agent"])
    assert orchestrator.traces["e2e-1"].summary()["trace_id"] == trace["trace_id"]


async def test_orchestrator_does_not_duplicate_registry_agents(mock_llm):
    from app.agents.base import get_agent_registry
    from app.orchestrator.graph import get_orchestrator

    before = get_agent_registry().get("financial_analyst")
    get_orchestrator()
    assert get_agent_registry().get("financial_analyst") is before


async def test_agents_share_tool_instances(mock_llm):
    from app.agents.base import get_agent_registry

    registry = get_agent_registry()
    fa = registry.get("financial_analyst")
    mr = registry.get("market_researcher")
    assert fa.tools is not mr.tools  # per-agent router (own provenance context)
    assert fa.tools.tools["web_search"] is mr.tools.tools["web_search"]


async def test_structured_run_with_tool_round(mock_llm):
    """run_with_structure: issue tree → retrieval → run() with a tool round."""
    from app.agents.base import get_agent_registry

    agent = get_agent_registry().get("financial_analyst")
    mock_llm.queue(
        # issue tree
        {
            "content": '```json\n{"hypothesis": "Acme is fairly valued", "branches": ['
            '{"id": "b1", "hypothesis": "Financial valuation and cash flow"},'
            '{"id": "b2", "hypothesis": "Strategic market growth"},'
            '{"id": "b3", "hypothesis": "Regulatory risk"},'
            '{"id": "b4", "hypothesis": "Operational integration"}]}\n```'
        },
        # analysis: one tool call, then the final JSON
        {
            "content": "",
            "function_calls": [
                {
                    "name": "financial_calculator",
                    "args": {"calculation_type": "multiple", "inputs": {"revenue": 10, "multiple": 3}},
                }
            ],
        },
        {"content": '{"summary": "ok", "reasoning": "valued at 30", "recommendation": "BUY"}'},
    )

    with start_trace("structured") as trace:
        out = await agent.run_with_structure("Value Acme Corp", {"deal_id": "s-1"})

    assert out.success
    assert out.issue_tree["hypothesis"] == "Acme is fairly valued"
    assert [b["id"] for b in out.issue_tree["sub_branches"]] == ["b1", "b2", "b3", "b4"]
    assert out.data["calculations"][0]["data"] == {"valuation": 30}
    assert trace.summary()["llm_calls"] == 3  # tree + tool round + answer
    assert trace.summary()["tool_calls"] == 1
