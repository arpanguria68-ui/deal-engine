"""
Run DealForge agents from the command line with full call tracing.

    # one agent, offline (no API keys needed)
    python -m app.core.harness.cli agent financial_analyst "Analyze Acme Corp" --provider mock

    # one agent on a real provider, with structured (issue-tree) execution
    python -m app.core.harness.cli agent market_researcher "Market for EV chargers" \
        --provider gemini --structured --context '{"target_company": "ChargePoint"}'

    # the full LangGraph deal workflow
    python -m app.core.harness.cli deal --target "Acme Corp" --provider mock

    # cap spend: refuse LLM calls beyond 40 calls / 300k tokens for the run
    python -m app.core.harness.cli --max-llm-calls 40 --max-tokens 300000 deal --target "Acme"

    # list registered agents
    python -m app.core.harness.cli list

Run from the backend/ directory. Prints the result followed by the trace
summary (LLM calls, tool calls, tokens, cache hits, fallbacks, per-agent
breakdown). --trace-out writes the full call-level trace as JSON.
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from app.core.harness.trace import RunBudget, RunTrace, agent_scope, start_trace


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    return obj


def _configure_logging(verbose: bool) -> None:
    """Send structlog output to stderr so stdout stays pure JSON."""
    import logging

    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if verbose else logging.WARNING
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def _setup_provider(provider: Optional[str]) -> None:
    if not provider:
        return
    from app.core.harness.mock_llm import (
        MOCK_PROVIDER,
        install_mock_provider,
        route_all_agents_to,
    )

    if provider == MOCK_PROVIDER:
        install_mock_provider()
    route_all_agents_to(provider)


def _emit(result: Any, trace: RunTrace, trace_out: Optional[str]) -> None:
    print(json.dumps(_jsonable(result), indent=2, default=str))
    print("\n── harness trace ──", file=sys.stderr)
    print(json.dumps(trace.summary(), indent=2), file=sys.stderr)
    if trace_out:
        with open(trace_out, "w") as f:
            json.dump(trace.to_dict(), f, indent=2, default=str)
        print(f"full trace written to {trace_out}", file=sys.stderr)


async def run_agent(
    name: str,
    task: str,
    context: Dict[str, Any],
    structured: bool,
    budget: Optional[RunBudget] = None,
) -> tuple:
    from app.agents.base import get_agent_registry

    agent = get_agent_registry().get(name)
    if agent is None:
        raise SystemExit(
            f"Unknown agent '{name}'. Available: {', '.join(get_agent_registry().list_agents())}"
        )
    with start_trace(f"agent:{name}", budget=budget) as trace, agent_scope(name):
        runner = agent.run_with_structure if structured else agent.run
        result = await runner(task, context)
    return result, trace


async def run_deal(
    target: str,
    deal_id: Optional[str],
    context: Dict[str, Any],
    budget: Optional[RunBudget] = None,
) -> tuple:
    from app.orchestrator.graph import get_orchestrator

    orchestrator = get_orchestrator()
    deal_id = deal_id or uuid.uuid4().hex[:8]
    final_state = await orchestrator.run_deal(
        deal_id=deal_id,
        deal_name=f"Deal-{target}",
        context={"target_company": target, "deal_id": deal_id, **context},
        budget=budget,
    )
    return final_state, orchestrator.traces[str(deal_id)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.core.harness.cli")
    parser.add_argument(
        "--provider",
        help="Route every agent to this provider (e.g. mock, gemini, openai, lmstudio)",
    )
    parser.add_argument("--trace-out", help="Write the full call-level trace JSON here")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--max-llm-calls", type=int, help="Budget: max LLM calls for the run")
    parser.add_argument("--max-tokens", type=int, help="Budget: max tokens for the run")
    sub = parser.add_subparsers(dest="command", required=True)

    p_agent = sub.add_parser("agent", help="Run a single agent")
    p_agent.add_argument("name")
    p_agent.add_argument("task")
    p_agent.add_argument("--context", default="{}", help="JSON context object")
    p_agent.add_argument(
        "--structured",
        action="store_true",
        help="Use run_with_structure (issue tree + retrieval + validation)",
    )

    p_deal = sub.add_parser("deal", help="Run the full deal workflow graph")
    p_deal.add_argument("--target", required=True, help="Target company name")
    p_deal.add_argument("--deal-id")
    p_deal.add_argument("--context", default="{}", help="Extra JSON context")

    sub.add_parser("list", help="List registered agents")

    # Allow --provider/--trace-out after the subcommand too.
    for p in (p_agent, p_deal):
        p.add_argument("--provider", dest="provider_sub")
        p.add_argument("--trace-out", dest="trace_out_sub")

    args = parser.parse_args(argv)
    provider = getattr(args, "provider_sub", None) or args.provider
    trace_out = getattr(args, "trace_out_sub", None) or args.trace_out
    _configure_logging(args.verbose)
    _setup_provider(provider)

    if args.command == "list":
        from app.agents.base import get_agent_registry

        for name in sorted(get_agent_registry().list_agents()):
            print(name)
        return 0

    context = json.loads(args.context)
    budget = (
        RunBudget(max_llm_calls=args.max_llm_calls, max_tokens=args.max_tokens)
        if args.max_llm_calls is not None or args.max_tokens is not None
        else None
    )
    if args.command == "agent":
        result, trace = asyncio.run(
            run_agent(args.name, args.task, context, args.structured, budget)
        )
    else:
        result, trace = asyncio.run(
            run_deal(args.target, args.deal_id, context, budget)
        )
    _emit(result, trace, trace_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
