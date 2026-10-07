"""
Agent tool-calling loop.

Replaces the inline loop that used to live in BaseAgent.generate_with_tools.
Compared to it, this loop:

- returns the model's answer directly once it stops calling tools, instead of
  paying for an extra "final synthesis" call on every tool-using turn
  (synthesis now only runs when the round budget is exhausted);
- runs the tool calls of a round concurrently, each with a timeout;
- re-uses results of identical calls (same tool + args) instead of
  re-executing them, and stops early when a round requests nothing new;
- only executes tools the agent is allowed to use (others are answered with
  a "not available" error the model sees on the next round);
- truncates large tool payloads before feeding them back to the model;
- parses ReAct JSON for local models with a brace-balanced scanner, so nested
  args work and plain JSON answers are not mistaken for tool calls;
- when the caller expects JSON and the final answer isn't parseable, makes
  one repair call asking the model to restate it as valid JSON.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.core.harness.trace import ToolCallRecord, current_trace

logger = structlog.get_logger()

# Providers that get prompt-based (ReAct) tool calling instead of native tools.
REACT_PROVIDERS = {"ollama", "lmstudio", "mistral"}

_TOOL_NAME_KEYS = ("command", "tool", "name", "call")
_TOOL_ARG_KEYS = ("args", "parameters", "params", "arguments")


@dataclass
class ToolLoopConfig:
    max_rounds: int = 3
    tool_timeout_s: float = 45.0
    max_result_chars: int = 4000
    # Max chars of a malformed answer echoed back in the JSON-repair call
    max_repair_chars: int = 12000


# ═══════════════════════════════════════════════
#  ReAct parsing
# ═══════════════════════════════════════════════


def extract_json_objects(text: str) -> List[str]:
    """Return top-level {...} substrings, respecting nesting and strings.

    Fenced ```json blocks are preferred when present.
    """
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced

    objects: List[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                objects.append(text[start : i + 1])
    return objects


def _loads_lenient(block: str) -> Optional[Any]:
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        pass
    repaired = re.sub(r",\s*([}\]])", r"\1", block.strip().rstrip(","))
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def parse_react_tool_calls(content: str, allowed: set) -> List[Dict[str, Any]]:
    """Extract tool calls from a local model's text output.

    A JSON object only counts as a call when it names a tool in `allowed`.
    """
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL)
    calls = []
    for block in extract_json_objects(content):
        parsed = _loads_lenient(block)
        if not isinstance(parsed, dict):
            continue
        name = next(
            (parsed[k] for k in _TOOL_NAME_KEYS if isinstance(parsed.get(k), str)),
            None,
        )
        if name not in allowed:
            continue
        args = next((parsed[k] for k in _TOOL_ARG_KEYS if k in parsed), {})
        if isinstance(args, str):
            args = _loads_lenient(args) or {}
        calls.append({"name": name, "args": args if isinstance(args, dict) else {}})
    return calls


def is_parseable_json(content: str) -> bool:
    """True if the content holds a JSON object/array (fenced, bare, or
    embedded in prose), tolerating trailing commas and <think> blocks."""
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.DOTALL).strip()
    if not content:
        return False
    candidates = re.findall(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    candidates.append(content)
    candidates.extend(extract_json_objects(content))
    return any(isinstance(_loads_lenient(c.strip()), (dict, list)) for c in candidates)


def build_react_instructions(tools: List[Dict]) -> str:
    return (
        "\n\nYou have access to the following tools:\n"
        + json.dumps([t.get("function", t) for t in tools], indent=2)
        + """

To use a tool, output a JSON block wrapped in Markdown like this:
```json
{
  "command": "tool_name",
  "args": {"arg1": "value1"}
}
```
You may output several such blocks to call several tools at once. Output only
the JSON block(s) to use tools, or your final answer if no tools are needed.
"""
    )


# ═══════════════════════════════════════════════
#  Loop
# ═══════════════════════════════════════════════


def _call_key(call: Dict[str, Any]) -> str:
    return call["name"] + ":" + json.dumps(call.get("args") or {}, sort_keys=True, default=str)


def _truncate(data: Any, limit: int) -> Any:
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        text = str(data)
    if len(text) <= limit:
        return data
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"


class ToolLoop:
    """Runs an LLM ⇄ tools conversation through the LLM gateway."""

    def __init__(
        self,
        gateway,
        tool_router,
        agent_name: str,
        config: Optional[ToolLoopConfig] = None,
    ):
        self.gateway = gateway
        self.tools = tool_router
        self.agent_name = agent_name
        self.config = config or ToolLoopConfig()

    async def _execute_one(self, call: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        try:
            result = await asyncio.wait_for(
                self.tools.execute(call["name"], call.get("args") or {}),
                timeout=self.config.tool_timeout_s,
            )
            out = {
                "name": call["name"],
                "success": result.success,
                "data": result.data,
                "error": result.error,
            }
        except asyncio.TimeoutError:
            out = {
                "name": call["name"],
                "success": False,
                "data": None,
                "error": f"Tool timed out after {self.config.tool_timeout_s:.0f}s",
            }
        except Exception as e:  # tool bugs must not kill the agent
            out = {"name": call["name"], "success": False, "data": None, "error": str(e)}

        trace = current_trace()
        if trace is not None:
            trace.record_tool(
                ToolCallRecord(
                    tool=call["name"],
                    agent=self.agent_name,
                    latency_ms=round((time.time() - started) * 1000, 1),
                    success=out["success"],
                    error=out["error"],
                )
            )
        return out

    async def _execute_round(
        self, calls: List[Dict[str, Any]], seen: Dict[str, Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Execute a round's calls concurrently. Returns (results, new_count)."""
        fresh: Dict[str, Dict[str, Any]] = {}
        for call in calls:
            key = _call_key(call)
            if key not in seen and key not in fresh:
                fresh[key] = call

        executed = await asyncio.gather(*(self._execute_one(c) for c in fresh.values()))
        seen.update(zip(fresh.keys(), executed))

        trace = current_trace()
        results = []
        for call in calls:
            key = _call_key(call)
            if key not in fresh and trace is not None:
                trace.record_tool(
                    ToolCallRecord(
                        tool=call["name"],
                        agent=self.agent_name,
                        latency_ms=0.0,
                        success=seen[key]["success"],
                        deduplicated=True,
                    )
                )
            results.append(seen[key])
        return results, len(fresh)

    def _feedback(self, results: List[Dict[str, Any]]) -> str:
        compact = [
            {**r, "data": _truncate(r["data"], self.config.max_result_chars)}
            for r in results
        ]
        return json.dumps(compact, indent=2, default=str)

    async def _repair_json(
        self, response: Dict[str, Any], provider: str, temperature: float
    ) -> Dict[str, Any]:
        """One retry asking the model to restate a malformed answer as JSON."""
        content = response.get("content", "") or ""
        logger.warning("json_repair_attempt", agent=self.agent_name, chars=len(content))
        repaired = await self.gateway.call(
            provider=provider,
            prompt=(
                "The following response was supposed to be a single valid JSON "
                "object but could not be parsed. Rewrite it as valid JSON, keeping "
                "all of its information. Output only the JSON.\n\n"
                + content[: self.config.max_repair_chars]
            ),
            system_prompt="You convert text into strictly valid JSON. Return only JSON.",
            temperature=temperature,
            agent=self.agent_name,
        )
        if not repaired.get("error") and is_parseable_json(repaired.get("content", "")):
            return {**response, "content": repaired["content"], "json_repaired": True}
        return response

    async def run(
        self,
        prompt: str,
        provider: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.0,
        expect_json: bool = True,
    ) -> Dict[str, Any]:
        tools = tools or []
        allowed = {t.get("function", t).get("name") for t in tools}
        use_react = bool(tools) and provider in REACT_PROVIDERS
        native_tools = tools if (tools and not use_react) else None
        if use_react:
            system_prompt = (system_prompt or "") + build_react_instructions(tools)

        seen: Dict[str, Dict[str, Any]] = {}
        accumulated: List[Dict[str, Any]] = []
        all_calls: List[Dict[str, Any]] = []
        current_prompt = prompt
        response: Dict[str, Any] = {}
        needs_synthesis = False

        for round_num in range(1, self.config.max_rounds + 1):
            response = await self.gateway.call(
                provider=provider,
                prompt=current_prompt,
                system_prompt=system_prompt,
                tools=native_tools,
                temperature=temperature,
                agent=self.agent_name,
            )
            if response.get("error"):
                needs_synthesis = False  # every provider failed; don't retry blindly
                break

            if use_react:
                calls = parse_react_tool_calls(response.get("content", ""), allowed)
            else:
                calls = response.get("function_calls") or []

            rejected = [
                {
                    "name": c.get("name"),
                    "success": False,
                    "data": None,
                    "error": f"Tool '{c.get('name')}' is not available to this agent",
                }
                for c in calls
                if c.get("name") not in allowed
            ]
            calls = [c for c in calls if c.get("name") in allowed]

            if not calls and not rejected:
                needs_synthesis = False
                break  # model answered without (further) tools

            if rejected:
                logger.warning(
                    "tool_calls_rejected",
                    agent=self.agent_name,
                    tools=[r["name"] for r in rejected],
                )
            results: List[Dict[str, Any]] = []
            new_count = 0
            if calls:
                logger.info(
                    "Tool calls detected",
                    agent=self.agent_name,
                    round=round_num,
                    calls=[c["name"] for c in calls],
                )
                results, new_count = await self._execute_round(calls, seen)
            # Rejections are fed back so the model can recover on the next round
            accumulated.extend(rejected + results)
            all_calls.extend(calls)
            needs_synthesis = True

            if calls and new_count == 0:
                break  # the model is repeating itself; nothing new to learn

            current_prompt = (
                f"{prompt}\n\n--- TOOL EXECUTION RESULTS (Round {round_num}) ---\n"
                f"{self._feedback(accumulated)}\n\n"
                "Based on these results, either request additional tool calls if you "
                "need more data, or provide your final comprehensive analysis in the "
                "requested JSON format."
            )

        if needs_synthesis:
            final = await self.gateway.call(
                provider=provider,
                prompt=(
                    f"{prompt}\n\n--- ALL TOOL RESULTS ---\n{self._feedback(accumulated)}"
                    "\n\nBased on all these results, provide your final comprehensive "
                    + (
                        "analysis in the requested JSON format. Ensure your output is purely JSON."
                        if expect_json
                        else "answer in the requested format."
                    )
                ),
                system_prompt=system_prompt,
                temperature=temperature,
                agent=self.agent_name,
            )
            response = {**response, **final}

        if (
            expect_json
            and not response.get("error")
            and not is_parseable_json(response.get("content", ""))
        ):
            response = await self._repair_json(response, provider, temperature)

        if accumulated:
            response["tool_results"] = accumulated
            response["function_calls"] = all_calls
        response.setdefault("provider_used", provider)
        return response
