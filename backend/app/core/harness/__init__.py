"""
Agent harness: the runtime layer agents execute through.

- tool_loop: LLM ⇄ tool calling loop used by BaseAgent.generate_with_tools
- trace:     per-run telemetry (LLM calls, tool calls, tokens, latency)
- mock_llm:  offline scripted LLM provider for tests and dry runs
- cli:       `python -m app.core.harness.cli` to run an agent or a deal
"""

from app.core.harness.trace import (
    RunTrace,
    agent_scope,
    current_agent,
    current_trace,
    start_trace,
)

__all__ = ["RunTrace", "agent_scope", "current_agent", "current_trace", "start_trace"]
