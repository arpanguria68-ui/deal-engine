"""
Run tracing for the agent harness.

A RunTrace collects every LLM call and tool call made while it is active.
It is carried in a contextvar, so it follows the work into asyncio tasks
spawned with gather()/create_task() without being passed around explicitly.

    with start_trace("deal-123", budget=RunBudget(max_llm_calls=40)) as trace:
        await orchestrator.run_deal(...)
    print(trace.summary())

A RunBudget caps LLM calls and/or tokens for the run; once it is spent the
gateway refuses further calls (they return an error result instead).
"""

import contextvars
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class RunBudget:
    """Spending cap for one run. None means unlimited."""

    max_llm_calls: Optional[int] = None
    max_tokens: Optional[int] = None

    def to_dict(self) -> Dict[str, Optional[int]]:
        return {"max_llm_calls": self.max_llm_calls, "max_tokens": self.max_tokens}


@dataclass
class LLMCallRecord:
    provider: str
    agent: Optional[str]
    latency_ms: float
    tokens_est: int
    cached: bool = False
    fallback_used: bool = False
    error: Optional[str] = None
    # Provider-reported counts, when the provider returns them
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


@dataclass
class ToolCallRecord:
    tool: str
    agent: Optional[str]
    latency_ms: float
    success: bool
    deduplicated: bool = False
    error: Optional[str] = None


@dataclass
class RunTrace:
    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    llm_calls: List[LLMCallRecord] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    budget: Optional[RunBudget] = None
    budget_blocked: int = 0
    # Calls admitted by the budget but not yet finished. Counted against the
    # call budget so parallel agents can't all pass the check at once.
    inflight: int = 0

    def record_llm(self, record: LLMCallRecord) -> None:
        self.llm_calls.append(record)

    def tokens_used(self) -> int:
        """Provider-reported tokens where available, estimates otherwise.
        Cache hits cost nothing."""
        total = 0
        for c in self.llm_calls:
            if c.cached:
                continue
            if c.input_tokens is not None or c.output_tokens is not None:
                total += (c.input_tokens or 0) + (c.output_tokens or 0)
            else:
                total += c.tokens_est
        return total

    def budget_exceeded(self) -> Optional[str]:
        """Reason string if the run's budget is spent, else None."""
        if self.budget is None:
            return None
        billable = sum(1 for c in self.llm_calls if not c.cached) + self.inflight
        if self.budget.max_llm_calls is not None and billable >= self.budget.max_llm_calls:
            return f"LLM call budget of {self.budget.max_llm_calls} reached"
        if self.budget.max_tokens is not None and self.tokens_used() >= self.budget.max_tokens:
            return f"token budget of {self.budget.max_tokens} reached"
        return None

    def record_tool(self, record: ToolCallRecord) -> None:
        self.tool_calls.append(record)

    def summary(self) -> Dict[str, Any]:
        end = self.finished_at or time.time()
        per_agent: Dict[str, Dict[str, Any]] = {}
        for c in self.llm_calls:
            a = per_agent.setdefault(
                c.agent or "unknown",
                {"llm_calls": 0, "tool_calls": 0, "tokens_est": 0, "llm_ms": 0.0},
            )
            a["llm_calls"] += 1
            a["tokens_est"] += c.tokens_est
            a["llm_ms"] += c.latency_ms
        for t in self.tool_calls:
            a = per_agent.setdefault(
                t.agent or "unknown",
                {"llm_calls": 0, "tool_calls": 0, "tokens_est": 0, "llm_ms": 0.0},
            )
            a["tool_calls"] += 1
        for a in per_agent.values():
            a["llm_ms"] = round(a["llm_ms"], 1)

        providers: Dict[str, int] = {}
        for c in self.llm_calls:
            providers[c.provider] = providers.get(c.provider, 0) + 1

        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "wall_ms": round((end - self.started_at) * 1000, 1),
            "llm_calls": len(self.llm_calls),
            "billable_llm_calls": sum(1 for c in self.llm_calls if not c.cached),
            "llm_errors": sum(1 for c in self.llm_calls if c.error),
            "cache_hits": sum(1 for c in self.llm_calls if c.cached),
            "fallbacks": sum(1 for c in self.llm_calls if c.fallback_used),
            "tokens_est": sum(c.tokens_est for c in self.llm_calls),
            "tokens_used": self.tokens_used(),
            "tokens_reported": any(
                c.input_tokens is not None or c.output_tokens is not None
                for c in self.llm_calls
            ),
            "tool_calls": len(self.tool_calls),
            "tool_failures": sum(1 for t in self.tool_calls if not t.success),
            "tool_dedup_hits": sum(1 for t in self.tool_calls if t.deduplicated),
            "providers": providers,
            "per_agent": per_agent,
            "budget": self.budget.to_dict() if self.budget else None,
            "budget_blocked_calls": self.budget_blocked,
            "running": self.finished_at is None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.summary(),
            "llm_call_log": [asdict(c) for c in self.llm_calls],
            "tool_call_log": [asdict(t) for t in self.tool_calls],
        }


_current_trace: contextvars.ContextVar[Optional[RunTrace]] = contextvars.ContextVar(
    "dealforge_run_trace", default=None
)
_current_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "dealforge_current_agent", default=None
)


def current_trace() -> Optional[RunTrace]:
    return _current_trace.get()


def current_agent() -> Optional[str]:
    return _current_agent.get()


@contextmanager
def start_trace(name: str, budget: Optional[RunBudget] = None) -> Iterator[RunTrace]:
    """Activate a new RunTrace (optionally budget-capped) for the enclosed block."""
    trace = RunTrace(name=name, budget=budget)
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        trace.finished_at = time.time()
        _current_trace.reset(token)


@contextmanager
def agent_scope(agent_name: str) -> Iterator[None]:
    """Attribute LLM/tool calls in the enclosed block to an agent."""
    token = _current_agent.set(agent_name)
    try:
        yield
    finally:
        _current_agent.reset(token)
