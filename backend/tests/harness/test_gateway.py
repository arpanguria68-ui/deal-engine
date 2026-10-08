"""Tests for LLMGateway routing, caching, retry and tracing."""

import httpx
import pytest

from app.core.harness.mock_llm import MockLLMClient
from app.core.harness.trace import agent_scope, start_trace
from app.core.llm import get_llm_client, register_llm_client, reset_llm_clients
from app.core.llm import llm_gateway as gw_mod


@pytest.fixture
def two_providers(monkeypatch):
    """Providers "mock" and "mock_b", with mock → mock_b as fallback chain."""
    primary, backup = MockLLMClient(), MockLLMClient()
    register_llm_client("mock", lambda: primary)
    register_llm_client("mock_b", lambda: backup)
    monkeypatch.setitem(gw_mod.FALLBACK_CHAIN, "mock", ["mock_b"])
    return primary, backup


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(gw_mod.asyncio, "sleep", instant)


def set_availability(monkeypatch, available):
    from app.core.llm.model_router import get_model_router

    async def is_available(provider):
        return available.get(provider, True)

    monkeypatch.setattr(get_model_router(), "is_provider_available", is_available)


async def test_temperature_and_max_tokens_reach_the_client(mock_llm, gateway):
    await gateway.call("mock", "p", temperature=0.2, max_tokens=123)
    assert mock_llm.calls[0]["temperature"] == 0.2
    assert mock_llm.calls[0]["max_tokens"] == 123


async def test_cache_hit_keeps_function_calls(mock_llm, gateway):
    mock_llm.tool_call("web_search", query="x")
    tools = [{"type": "function", "function": {"name": "web_search"}}]

    first = await gateway.call("mock", "p", tools=tools, temperature=0)
    second = await gateway.call("mock", "p", tools=tools, temperature=0)

    assert len(mock_llm.calls) == 1
    assert second["cached"] is True
    assert second["function_calls"] == first["function_calls"]


async def test_cache_key_includes_tools_and_skips_nonzero_temperature(mock_llm, gateway):
    await gateway.call("mock", "p", temperature=0)
    await gateway.call("mock", "p", temperature=0, tools=[{"function": {"name": "t"}}])
    await gateway.call("mock", "p", temperature=0.7)
    await gateway.call("mock", "p", temperature=0.7)
    assert len(mock_llm.calls) == 4


def test_cache_is_lru_bounded():
    cache = gw_mod.ResponseCache(max_size=2)
    msgs = lambda i: [{"role": "user", "content": str(i)}]  # noqa: E731
    cache.set("p", msgs(1), "m", {"content": "1"})
    cache.set("p", msgs(2), "m", {"content": "2"})
    cache.get("p", msgs(1), "m")  # touch 1 → 2 becomes LRU
    cache.set("p", msgs(3), "m", {"content": "3"})
    assert cache.get("p", msgs(2), "m") is None
    assert cache.get("p", msgs(1), "m")["content"] == "1"


async def test_unavailable_provider_is_skipped_without_a_call(
    two_providers, gateway, monkeypatch
):
    primary, backup = two_providers
    set_availability(monkeypatch, {"mock": False, "mock_b": True})

    resp = await gateway.call("mock", "p")

    assert primary.calls == []
    assert len(backup.calls) == 1
    assert resp["provider_used"] == "mock_b"
    assert resp["fallback_used"] is True


async def test_failed_call_falls_back_along_chain(two_providers, gateway):
    primary, backup = two_providers
    primary.queue(ValueError("bad request"))

    resp = await gateway.call("mock", "p")

    assert resp["provider_used"] == "mock_b"
    assert resp["fallback_used"] is True
    assert "error" not in resp


async def test_all_providers_failing_returns_error_result(two_providers, gateway):
    primary, backup = two_providers
    primary.queue(ValueError("boom"))
    backup.queue(ValueError("boom too"))

    resp = await gateway.call("mock", "p")

    assert resp["content"].startswith("[Error]")
    assert resp["error"]


async def test_network_errors_retry_a_bounded_number_of_times(two_providers, gateway):
    primary, backup = two_providers
    err = httpx.ConnectError("refused")
    primary.queue(err, err, err, err, err, err)

    resp = await gateway.call("mock", "p")

    assert len(primary.calls) == gw_mod.MAX_NETWORK_RETRIES + 1
    assert resp["provider_used"] == "mock_b"


async def test_rate_limit_status_is_retried(mock_llm, gateway):
    class RateLimited(Exception):
        status_code = 429

    mock_llm.queue(RateLimited(), RateLimited(), {"content": "ok"})
    resp = await gateway.call("mock", "p")
    assert resp["content"] == "ok"
    assert len(mock_llm.calls) == 3


async def test_calls_are_recorded_on_the_active_trace(mock_llm, gateway):
    with start_trace("t") as trace:
        with agent_scope("financial_analyst"):
            await gateway.call("mock", "p", temperature=0)
            await gateway.call("mock", "p", temperature=0)

    summary = trace.summary()
    assert summary["llm_calls"] == 2
    assert summary["cache_hits"] == 1
    assert summary["per_agent"]["financial_analyst"]["llm_calls"] == 2


def test_llm_clients_are_pooled_and_resettable():
    built = []
    register_llm_client("pooled", lambda: built.append(1) or MockLLMClient())

    a = get_llm_client("pooled")
    b = get_llm_client("pooled")
    assert a is b and len(built) == 1

    reset_llm_clients()
    assert get_llm_client("pooled") is not a
    assert len(built) == 2


async def test_cloud_provider_without_key_is_unavailable(monkeypatch):
    from app.config import get_settings
    from app.core.llm.model_router import get_model_router

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(get_settings(), "MISTRAL_API_KEY", None)
    assert await get_model_router().is_provider_available("mistral") is False

    monkeypatch.setattr(get_settings(), "MISTRAL_API_KEY", "sk-test")
    assert await get_model_router().is_provider_available("mistral") is True
