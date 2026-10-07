"""Tests for the agent tool-calling loop (app.core.harness.tool_loop)."""

import asyncio
import json
import time

from app.core.harness.tool_loop import (
    ToolLoop,
    ToolLoopConfig,
    extract_json_objects,
    parse_react_tool_calls,
)
from app.core.harness.trace import start_trace
from app.core.tools.tool_router import BaseTool, ToolResult, ToolRouter


class EchoTool(BaseTool):
    def __init__(self, name="echo", delay=0.0):
        super().__init__(name=name, description="Echo the input back")
        self.delay = delay
        self.calls = 0

    def get_parameters_schema(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str = "") -> ToolResult:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return ToolResult(success=True, data={"echo": text})


def make_router(*tools):
    router = ToolRouter()
    for t in tools:
        router.register_tool(t)
    return router


def schemas(router):
    return router.list_tools()


async def test_answer_without_tools_is_one_call(mock_llm, gateway):
    tool = EchoTool()
    router = make_router(tool)
    mock_llm.queue({"content": '{"answer": 42}'})

    loop = ToolLoop(gateway, router, "tester")
    resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert resp["content"] == '{"answer": 42}'
    assert len(mock_llm.calls) == 1
    assert "tool_results" not in resp
    assert tool.calls == 0


async def test_no_redundant_synthesis_call(mock_llm, gateway):
    """tool round → final answer must cost 2 LLM calls, not 3."""
    tool = EchoTool()
    router = make_router(tool)
    mock_llm.tool_call("echo", text="hi").queue({"content": '{"final": true}'})

    loop = ToolLoop(gateway, router, "tester")
    resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert len(mock_llm.calls) == 2
    assert resp["content"] == '{"final": true}'
    assert resp["tool_results"][0]["data"] == {"echo": "hi"}
    assert '"echo": "hi"' in mock_llm.calls[1]["prompt"]


async def test_round_budget_exhausted_triggers_synthesis(mock_llm, gateway):
    tool = EchoTool()
    router = make_router(tool)
    mock_llm.tool_call("echo", text="a").tool_call("echo", text="b")
    mock_llm.queue({"content": '{"synth": 1}'})

    loop = ToolLoop(gateway, router, "tester", ToolLoopConfig(max_rounds=2))
    resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert len(mock_llm.calls) == 3
    assert resp["content"] == '{"synth": 1}'
    assert mock_llm.calls[2]["tools"] is None  # synthesis offers no tools
    assert [r["data"]["echo"] for r in resp["tool_results"]] == ["a", "b"]


async def test_repeated_call_is_deduplicated_and_stops_loop(mock_llm, gateway):
    tool = EchoTool()
    router = make_router(tool)
    mock_llm.tool_call("echo", text="same").tool_call("echo", text="same")
    mock_llm.queue({"content": '{"synth": 1}'})

    with start_trace("t") as trace:
        loop = ToolLoop(gateway, router, "tester", ToolLoopConfig(max_rounds=5))
        resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert tool.calls == 1  # second identical request reused the result
    assert len(mock_llm.calls) == 3  # round 1, round 2 (repeat), synthesis
    assert resp["content"] == '{"synth": 1}'
    assert trace.summary()["tool_dedup_hits"] == 1


async def test_disallowed_tool_is_not_executed(mock_llm, gateway):
    allowed, forbidden = EchoTool("echo"), EchoTool("secret")
    router = make_router(allowed, forbidden)
    only_echo = [s for s in schemas(router) if s["function"]["name"] == "echo"]
    mock_llm.tool_call("secret", text="x").queue({"content": "done"})

    loop = ToolLoop(gateway, router, "tester")
    resp = await loop.run("q", provider="mock", tools=only_echo, expect_json=False)

    assert forbidden.calls == 0
    assert resp["content"] == "done"
    assert len(mock_llm.calls) == 2  # rejection fed back, model then answers
    assert resp["tool_results"][0]["success"] is False
    assert "not available" in mock_llm.calls[1]["prompt"]


async def test_tools_in_a_round_run_concurrently(mock_llm, gateway):
    a, b = EchoTool("slow_a", delay=0.3), EchoTool("slow_b", delay=0.3)
    router = make_router(a, b)
    mock_llm.queue(
        {
            "content": "",
            "function_calls": [
                {"name": "slow_a", "args": {"text": "1"}},
                {"name": "slow_b", "args": {"text": "2"}},
            ],
        },
        {"content": "ok"},
    )

    loop = ToolLoop(gateway, router, "tester")
    started = time.monotonic()
    await loop.run("q", provider="mock", tools=schemas(router))
    assert time.monotonic() - started < 0.55  # sequential would be ≥ 0.6s


async def test_tool_timeout_becomes_failed_result(mock_llm, gateway):
    tool = EchoTool("slow", delay=1.0)
    router = make_router(tool)
    mock_llm.tool_call("slow", text="x").queue({"content": "ok"})

    loop = ToolLoop(gateway, router, "tester", ToolLoopConfig(tool_timeout_s=0.05))
    resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert resp["tool_results"][0]["success"] is False
    assert "timed out" in resp["tool_results"][0]["error"]


async def test_large_tool_results_are_truncated_in_prompt(mock_llm, gateway):
    class BigTool(EchoTool):
        async def execute(self, text: str = "") -> ToolResult:
            return ToolResult(success=True, data={"blob": "x" * 50_000})

    router = make_router(BigTool("big"))
    mock_llm.tool_call("big").queue({"content": "ok"})

    loop = ToolLoop(gateway, router, "tester", ToolLoopConfig(max_result_chars=1000))
    await loop.run("q", provider="mock", tools=schemas(router))

    follow_up = mock_llm.calls[1]["prompt"]
    assert "[truncated" in follow_up
    assert len(follow_up) < 5_000


async def test_react_mode_for_local_providers(mock_llm, gateway, monkeypatch):
    """Local providers get tools via prompt and are parsed from text."""
    from app.core.harness import tool_loop

    monkeypatch.setattr(tool_loop, "REACT_PROVIDERS", {"mock"})
    tool = EchoTool()
    router = make_router(tool)
    mock_llm.queue(
        {"content": 'Let me check.\n```json\n{"command": "echo", "args": {"text": "r"}}\n```'},
        {"content": '{"final": 1}'},
    )

    loop = ToolLoop(gateway, router, "tester")
    resp = await loop.run("q", provider="mock", tools=schemas(router))

    assert mock_llm.calls[0]["tools"] is None  # no native tools sent
    assert "You have access to the following tools" in mock_llm.calls[0]["system_prompt"]
    assert tool.calls == 1
    assert resp["content"] == '{"final": 1}'


# ── ReAct parsing ──


def test_extract_json_objects_handles_nesting_and_strings():
    text = 'pre {"a": {"b": [1, {"c": "}"}]}} mid {"d": 2} post'
    objs = extract_json_objects(text)
    assert [json.loads(o) for o in objs] == [{"a": {"b": [1, {"c": "}"}]}}, {"d": 2}]


def test_parse_react_ignores_json_that_is_not_a_known_tool():
    # A final answer that happens to contain a "name" key must not be a call.
    content = '{"name": "Acme Corp", "valuation": 100}'
    assert parse_react_tool_calls(content, {"web_search"}) == []


def test_parse_react_nested_args_think_tags_and_trailing_commas():
    content = (
        "<think>{\"command\": \"web_search\"}</think>"
        '{"tool": "financial_calculator", "parameters": '
        '{"calculation_type": "dcf", "inputs": {"cash_flows": [1, 2],},},}'
    )
    calls = parse_react_tool_calls(content, {"financial_calculator", "web_search"})
    assert calls == [
        {
            "name": "financial_calculator",
            "args": {"calculation_type": "dcf", "inputs": {"cash_flows": [1, 2]}},
        }
    ]


def test_parse_react_double_encoded_args():
    content = '{"command": "echo", "args": "{\\"text\\": \\"hi\\"}"}'
    assert parse_react_tool_calls(content, {"echo"}) == [
        {"name": "echo", "args": {"text": "hi"}}
    ]
