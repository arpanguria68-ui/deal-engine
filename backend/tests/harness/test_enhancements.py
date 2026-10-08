"""Tests for run budgets, token accounting, JSON repair, context isolation,
and workflow-level savings."""

import asyncio

from app.agents.base import AgentOutput, BaseAgent
from app.core.harness.tool_loop import ToolLoop, is_parseable_json
from app.core.harness.trace import RunBudget, start_trace
from app.core.tools.tool_router import ToolRouter


# ── Budget & token accounting ──


async def test_budget_blocks_calls_once_spent(mock_llm, gateway):
    with start_trace("t", budget=RunBudget(max_llm_calls=2)) as trace:
        first = await gateway.call("mock", "a")
        second = await gateway.call("mock", "b")
        third = await gateway.call("mock", "c")

    assert "error" not in first and "error" not in second
    assert third["error"] == "budget_exceeded"
    assert len(mock_llm.calls) == 2
    summary = trace.summary()
    assert summary["llm_calls"] == 2
    assert summary["budget_blocked_calls"] == 1
    assert summary["budget"] == {"max_llm_calls": 2, "max_tokens": None}


async def test_budget_holds_under_concurrent_calls(gateway):
    """Parallel agents must not all pass the check before any call records."""
    from app.core.llm import register_llm_client

    class SlowClient:
        calls = 0

        async def generate(self, prompt, **kwargs):
            SlowClient.calls += 1
            await asyncio.sleep(0.02)  # the window in which others check the budget
            return {"content": "ok"}

    register_llm_client("slow", SlowClient)
    with start_trace("t", budget=RunBudget(max_llm_calls=2)) as trace:
        results = await asyncio.gather(
            *(gateway.call("slow", f"p{i}") for i in range(6))
        )

    assert sum(1 for r in results if r.get("error") == "budget_exceeded") == 4
    assert SlowClient.calls == 2
    assert trace.inflight == 0


async def test_cache_hits_do_not_spend_budget(mock_llm, gateway):
    with start_trace("t", budget=RunBudget(max_llm_calls=1)):
        await gateway.call("mock", "same", temperature=0)
        hit = await gateway.call("mock", "same", temperature=0)
    assert hit["cached"] is True


async def test_token_budget_uses_provider_reported_usage(mock_llm, gateway):
    mock_llm.queue(
        {"content": "x", "usage": {"input_tokens": 900, "output_tokens": 200}},
        {"content": "y"},
    )
    with start_trace("t", budget=RunBudget(max_tokens=1000)) as trace:
        await gateway.call("mock", "a")
        blocked = await gateway.call("mock", "b")

    assert blocked["error"] == "budget_exceeded"
    summary = trace.summary()
    assert summary["tokens_used"] == 1100
    assert summary["tokens_reported"] is True


async def test_budget_exhaustion_stops_tool_loop_cleanly(mock_llm, gateway):
    router = ToolRouter()
    mock_llm.queue({"content": '{"a": 1}'})
    with start_trace("t", budget=RunBudget(max_llm_calls=0)):
        resp = await ToolLoop(gateway, router, "tester").run("q", provider="mock")
    assert resp["error"] == "budget_exceeded"
    assert mock_llm.calls == []


# ── JSON repair ──


def test_is_parseable_json():
    assert is_parseable_json('{"a": 1}')
    assert is_parseable_json('Here you go:\n```json\n{"a": [1, 2,],}\n```')
    assert is_parseable_json('<think>hmm</think> prefix {"a": {"b": 2}} suffix')
    assert not is_parseable_json("The company looks strong.")
    assert not is_parseable_json('{"a": 1')
    assert not is_parseable_json("")


async def test_malformed_answer_gets_one_repair_call(mock_llm, gateway):
    mock_llm.queue(
        {"content": "Revenue is $10M and growing 20%."},
        {"content": '{"revenue": 10, "growth": 0.2}'},
    )
    resp = await ToolLoop(gateway, ToolRouter(), "tester").run("q", provider="mock")

    assert len(mock_llm.calls) == 2
    assert resp["content"] == '{"revenue": 10, "growth": 0.2}'
    assert resp["json_repaired"] is True
    assert "Revenue is $10M" in mock_llm.calls[1]["prompt"]


async def test_failed_repair_keeps_original_answer(mock_llm, gateway):
    mock_llm.queue({"content": "prose"}, {"content": "still prose"})
    resp = await ToolLoop(gateway, ToolRouter(), "tester").run("q", provider="mock")
    assert resp["content"] == "prose"
    assert "json_repaired" not in resp


async def test_no_repair_when_json_not_expected(mock_llm, gateway):
    mock_llm.queue({"content": "A prose memo."})
    resp = await ToolLoop(gateway, ToolRouter(), "tester").run(
        "q", provider="mock", expect_json=False
    )
    assert resp["content"] == "A prose memo."
    assert len(mock_llm.calls) == 1


# ── Agent context isolation ──


class ContextProbeAgent(BaseAgent):
    name = "context_probe"
    description = "test agent"

    async def run(self, task, context=None):
        self._current_context = context
        await asyncio.sleep(0.05)  # let the other run overwrite, if it could
        return AgentOutput(
            success=True, data=dict(self._current_context), reasoning="", confidence=1
        )


async def test_concurrent_runs_of_one_agent_keep_their_own_context(mock_llm):
    agent = ContextProbeAgent()
    a, b = await asyncio.gather(
        agent.run("t", {"sector": "tech"}), agent.run("t", {"sector": "energy"})
    )
    assert a.data["sector"] == "tech"
    assert b.data["sector"] == "energy"


def test_issue_tree_context_is_compacted(mock_llm):
    agent = ContextProbeAgent()
    rendered = agent._compact_context(
        {
            "target_company": "Acme",
            "skill_context": "x" * 50_000,
            "sector_prompt": "y" * 10_000,
            "notes": "z" * 5_000,
            "empty": None,
        }
    )
    assert "Acme" in rendered
    assert "skill_context" not in rendered and "sector_prompt" not in rendered
    assert "empty" not in rendered
    assert len(rendered) <= 3000


# ── Workflow ──


async def test_market_research_is_not_repeated_on_first_pass(mock_llm):
    from app.orchestrator.graph import get_orchestrator

    final = await get_orchestrator().run_deal(
        deal_id="reuse-1",
        deal_name="Deal-Acme",
        context={"target_company": "Acme Corp", "deal_id": "reuse-1"},
    )
    per_agent = final["harness_trace"]["per_agent"]
    assert per_agent["market_researcher"]["llm_calls"] == 1  # was 2
    assert final["agent_states"]["market_researcher"] == "completed"


async def test_trace_is_visible_while_the_deal_runs(mock_llm):
    from app.orchestrator.graph import get_orchestrator

    orchestrator = get_orchestrator()
    seen = {}

    def peek(request):
        trace = orchestrator.traces.get("live-1")
        seen["running"] = trace is not None and trace.summary()["running"]
        return {"content": '{"summary": "ok"}'}

    mock_llm.queue(peek)
    final = await orchestrator.run_deal(
        deal_id="live-1",
        deal_name="Deal-Live",
        context={"target_company": "Acme Corp", "deal_id": "live-1"},
    )
    assert seen["running"] is True
    assert final["harness_trace"]["running"] is False


async def test_deal_run_respects_budget(mock_llm):
    from app.orchestrator.graph import get_orchestrator

    final = await get_orchestrator().run_deal(
        deal_id="budget-1",
        deal_name="Deal-Budget",
        context={"target_company": "Acme Corp", "deal_id": "budget-1"},
        budget=RunBudget(max_llm_calls=3),
    )
    trace = final["harness_trace"]
    assert trace["billable_llm_calls"] == 3
    assert trace["budget_blocked_calls"] > 0
    assert final["current_stage"] == "completed"  # degrades, doesn't crash
