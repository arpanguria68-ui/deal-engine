# Agent Harness — Audit & Usage

This document covers (1) the inefficiency audit of the agentic flow and (2) the
upgraded harness that agents now run through: what changed, how to use it, and
what is still open.

---

## 1. Audit findings

### Fixed in this change

#### LLM layer (`app/core/llm/`)

| # | Finding | Impact | Fix |
|---|---------|--------|-----|
| 1 | `get_llm_client()` built a **new client on every call** (new `AsyncOpenAI` / `httpx.AsyncClient`, never closed; `genai.configure` each time). | Socket/connection-pool leak, repeated SDK setup on every LLM call. | Clients pooled per provider; `reset_llm_clients()` called when settings change. |
| 2 | Gateway **never forwarded `temperature` / `max_tokens`** to clients; clients hard-coded 0.7. `OpenAIClient`/`MistralClient.generate()` didn't accept `temperature` (→ `TypeError` from `FinancialAnalystAgent.run_valuation`). | "Deterministic" temperature-0 calls actually sampled at 0.7, and the cache served those sampled answers as deterministic. | All clients accept and honor both; gateway passes them through. |
| 3 | Response cache stored only `content` (a cached tool-calling turn **lost its `function_calls`**), ignored `tools` in the key, and evicted with an O(n) scan (not LRU). | Wrong behavior on cache hits; slow eviction. | `OrderedDict` LRU cache storing `content` + `function_calls`, keyed on tools too. |
| 4 | Default routing sends ~18 agents to **LM Studio**. When it isn't running (e.g. Cloud Run / Docker), `generate_with_tools` ignored health, so **every call failed**, then fell back to Ollama (also local, also down) and returned an `[Error]` string as the "analysis". | Whole pipeline silently produced error text off-box. | Gateway routing is availability-aware: local servers are health-probed (cached 30 s), cloud vendors without an API key are skipped, and the fallback chain is walked for both quota *and* call failures. |
| 5 | Retries only covered HTTP status codes; timeouts/connection resets weren't retried at all. | Transient network blips failed whole agents. | Network errors retried (bounded to 2) separately from 429/5xx. |
| 6 | No concurrency limit per provider; 4+ parallel agents hit a single-request local server simultaneously. | Timeouts on local models. | Per-provider semaphores (2 for Ollama/LM Studio, 8 for cloud). |
| 7 | Vertex AI path used `os` without importing it. | `NameError` whenever provider = `vertex` with an API key. | Import added. |

#### Agent tool loop (`BaseAgent.generate_with_tools` → `app/core/harness/tool_loop.py`)

| # | Finding | Impact | Fix |
|---|---------|--------|-----|
| 8 | After any tool round, the loop always made an **extra "final synthesis" LLM call**, even when the model had already answered. | +1 LLM call (≈ +50 % cost) on every tool-using turn. | Synthesis only runs when the round budget is exhausted. Tool round → answer is now 2 calls, not 3. |
| 9 | Tool calls executed **sequentially**, with **no timeout**. | Slow rounds; one hung API stalled the agent until the agent-level timeout killed everything. | Calls in a round run concurrently, each with a 45 s timeout (failure becomes a result the model sees). |
| 10 | Identical tool calls were re-executed every round; whole tool payloads were re-sent untruncated. | Wasted API quota and prompt tokens; context overflow on local models. | Same tool+args reuses the earlier result; loop stops when a round asks for nothing new; payloads truncated to 4 000 chars in prompts. |
| 11 | ReAct parsing (local models) used regex `\{.*?\}`, which **broke on nested args** and treated **any JSON answer with a `name` key** (e.g. `{"name": "Acme Corp", ...}`) as a tool call. Leftover debug `print`. | Wrong tool calls; final answers swallowed. | Brace-balanced scanner; a block only counts if it names a tool the agent has; `<think>` blocks stripped. |
| 12 | `AGENT_TOOL_MAP` was enforced when *listing* tools but not when *executing* them. | Model could call any registered tool. | Disallowed calls are refused and the refusal is fed back to the model. |
| 13 | 6 agent call sites called `self.llm.generate()` directly, bypassing the gateway. | No rate limiting, fallback, caching or tracing on those calls. | New `BaseAgent.llm_generate()`; all sites routed through it. |
| 14 | Issue-tree JSON parsed with `.strip("```json")` (character-set strip, not prefix strip); per-branch retrieval ran sequentially. | Fragile parsing → fallback tree; serial I/O. | Uses `extract_and_parse_json`; branch retrieval via `asyncio.gather`. |

#### Construction / startup

| # | Finding | Impact | Fix |
|---|---------|--------|-----|
| 15 | Every agent instance built its **own ToolRouter with ~38 tools** (and re-imported tool modules, logging each). `DealOrchestrator` then **re-instantiated 21 agents** that `get_agent_registry()` had already built. | ~50 agents × 38 tools at startup; thousands of log lines; duplicated warnings. | Stateless tools are built once and shared; each agent keeps a light router (own provenance context + document search). Orchestrator only registers missing agents. |
| 16 | `AgentQualityStore.initialize()` ran `CREATE TABLE` DDL on **every agent run**. | Extra SQLite round trips per run. | Idempotent per DB path per process. |

#### Workflow correctness bugs found by running the flow through the harness

| # | Bug | Impact | Fix |
|---|-----|--------|-----|
| 17 | `recursion_limit` was set to `max_iterations` (10), but the happy path through the graph is ~16 node visits. | **Every `/api/v1/deals/{id}/run` ended in `GRAPH_RECURSION_LIMIT`.** | Separate `recursion_limit` config (default 60, covers loop-backs). |
| 18 | Initial state sets agent outputs to `None`, so `state.get("x_output", {})` returned `None`; `_should_continue_after_red_team` called `.get` on it. | Any failed agent crashed the whole workflow. | All 25 lookups made `None`-safe; Red Team normalizes inputs. |
| 19 | `BusinessAnalystAgent` built `AgentOutput` without the required `confidence` in **both** the success and error paths. | Agent could never return; report formatting always failed. | `confidence` supplied. |
| 20 | `_node_parallel_analysis` zipped results against the full agent list rather than the scheduled ones. | One missing agent shifted results onto the wrong output keys. | Zips against the scheduled list; empty results marked `ERROR`. |

### Round 2 enhancements

| # | Change | Why |
|---|--------|-----|
| 21 | **Per-run budget** (`RunBudget(max_llm_calls, max_tokens)`). The gateway refuses calls once a run's budget is spent. In-flight calls are reserved, so parallel agents can't overshoot. Cache hits are free. Available via `run_deal(budget=)`, `POST /deals/{id}/run?max_llm_calls=&max_tokens=`, the CLI's `--max-llm-calls/--max-tokens`, or the workflow config `run_budget`. | Hard cost ceiling per deal. A spent budget degrades the run instead of crashing it. |
| 22 | **Real token usage.** Clients return the provider's `usage` (OpenAI-compatible, Gemini, Ollama). The gateway and traces use it instead of the 4-chars/token estimate when present (`tokens_used`, `tokens_reported`). | Accurate rate limiting, budgets and dashboards. |
| 23 | **No stacked retries.** The SDK's own retries are off (`max_retries=0`) on OpenAI, LM Studio and NVIDIA clients, so only the gateway retries. | One 429 no longer means up to 3 × 6 attempts. |
| 24 | **JSON repair.** When an agent expects JSON (the default for `generate_with_tools`) and the final answer doesn't parse, the loop makes one repair call. The investment memo opts out because it's prose. | Fewer agents falling back to `{"reasoning": <raw text>}`. |
| 25 | **Market research runs once.** On the first analysis pass, the screening output is reused (config `reuse_screening_market_output`). It still re-runs on loop-backs or when reviewer feedback targets it. | −1 full agent run per deal. |
| 26 | **Compact issue-tree prompt.** Skill docs, sector prompts and bulky payloads are dropped, values truncated, total capped at 3 000 chars. | The planning call previously embedded the whole context. |
| 27 | **Agent run context isolated per task.** `_current_context` is now ContextVar-backed. | Registry agents are shared, so concurrent runs overwrote each other's sector prompt and context. |
| 28 | **Live progress.** Traces are registered when a run starts, and `running` shows in summaries. | `GET /api/v1/harness/traces/{deal_id}` can be polled mid-run. |
| 29 | **Registry agents in the API.** The API reuses the registry's Project Manager and OFAS supervisor instead of building new ones per request. | No per-request agent/tool construction. |
| 30 | **Compiler bug.** `ReportCompilerAgent` read `res["result"]["data"]`, but tool results have always been `{name, success, data}`. | Generated report files were never returned. |
| 31 | **Repo hygiene.** Committed logs, `*_out.txt` dumps and `.bak` files are untracked and ignored. | Repo noise. |

### Round 3: decision layer and usage guardrails

Each problem below was reproduced by running deals through the harness with
one agent's output replaced.

| Scenario | Before | After |
|---|---|---|
| Scoring agent fails | Workflow crashed (`None >= 75`) | HOLD + human review |
| One analysis agent errors | Whole deal crashed: "retry" re-ran screening, then `"REJECT" in None` | Only the failed agent is retried once, then the run continues without it; verdict capped |
| Red Team severity-5 "fraud indicators" survive the loop-back, score 85 | **PROCEED - Strong investment opportunity** | HOLD + human review |
| Score 80, critical risk | HOLD, no escalation | HOLD + human review |
| HaluGate throws | Silently treated as passed | Recorded as unverified; verdict capped at CAUTION |
| HaluGate blocks | Decision node skipped; no decision record | Goes through the decision node → BLOCKED with reasons |

The decision now lives in `app/core/decision/policy.py`, a pure,
unit-tested function. The score sets a base verdict; guardrails can only cap
it, never upgrade it:

| Gate | Cap | Human review |
|---|---|---|
| HaluGate contradiction | BLOCKED | yes |
| No score | HOLD | yes |
| Red Team severity ≥ 4 (configurable) | HOLD | yes |
| Critical risk | HOLD | yes |
| Data coverage < 30 % | HOLD | — |
| Core agent (financial/legal) failed | HOLD | yes |
| Other agent failed / material cross-agent contradiction / narrative unverified | PROCEED WITH CAUTION | — |
| `require_human_approval: true` | — | always |

Results are recorded in the deal state:
- `decision`: verdict, base verdict, score, risk, reasons, and the caps applied.
- `awaiting_decision` and `decision_request`: used when human review is needed.
- `degraded_agents`: agents that failed and were skipped.

Thresholds are set through the workflow config `decision_policy` (the fields
of `DecisionPolicy`). The previously dead config keys
`require_human_approval` and `max_tokens_month` are now enforced.

**Usage guardrails**

| Finding | Fix |
|---|---|
| No authentication on any endpoint. Anyone reaching the server could change API keys (`POST /settings`), rate limits, or proxy arbitrary LLM calls (`/gateway/call`). | Opt-in API key: set `DEALFORGE_API_KEY` and every `/api/` route needs `Authorization: Bearer <key>` or `X-API-Key`. Health probes stay public. A startup warning is logged while unset. |
| No per-client limit; one client could exhaust vendor quota for everyone. | 14 LLM-spending endpoints share a per-client sliding window (`DEALFORGE_LLM_RPM`, default 30/min) and return 429 with `Retry-After`. |
| Prompt guard covered 5 chat endpoints. `/agents/run`, `/gateway/call`, `/gateway/hybrid`, `/codex/generate` and OFAS missions were unguarded. | All of them are guarded and return 400 on failure. |
| The guard blocked "attack", "exploit", "hack" and "virus", rejecting normal diligence prompts ("exploit synergies", "cyber-attack exposure", a virus-diagnostics target). The length limit only warned. Full prompts were logged. | It now blocks injection and secret-exfiltration attempts and control characters, enforces the length limit (`DEALFORGE_MAX_PROMPT_CHARS`, default 8000), and logs only length + hash. |
| `/gateway/limits` took unvalidated values for any vendor name, and *replaced* the limiter, zeroing its counters. Re-posting reset rate limiting. | Validated, and updates in place (`set_vendor_limits`). Settings saves use it too. |
| `/gateway/call` passed `max_tokens`/`temperature` through unchecked and returned the raw SDK response. | Values are clamped (≤ 8192 tokens, 0–2) and `raw_response` is stripped. |
| No per-deal spend ceiling by default. | Default `run_budget` of 200 LLM calls as a runaway backstop. |

**Still open in this area:** HaluGate only checks the scorer's short
recommendation strings against the financial output. It skips whenever those
are empty, so most runs are "unverified". Pointing it at the agents' own
narratives (financial and market reasoning) would make it a real check. The
API key is opt-in so the current frontend keeps working; the frontend needs to
send it before you turn it on.

### Still open (recommendations, not changed here)

- **Tool rounds replay the whole prompt.** Clients take a single `prompt` string, so every round re-sends the original prompt plus all results. Moving to multi-turn `messages` would let provider prompt caching apply.
- **The issue tree is still one extra LLM call per agent** (now with a compact prompt). Consider making it opt-in per deal stage.
- **Default routing is local-first** (LM Studio). It degrades gracefully now, but in container deployments the default should be a cloud provider.
- **Tracked data and outputs.** `backend/data/agent_quality.db` is tracked and mutated by every run, and generated `.pptx` outputs are tracked. Left as is because untracking them would delete local copies on pull. Decide whether they should live in git.
- **Existing test suites are broken** independently of these changes: `backend/tests/evals` is 20 failed / 3 passed before and after (MCP signature mismatches, `NameError`s, imports). `app/main.py` (3 000 lines) would benefit from splitting into routers.

---

## 2. The harness

```
app/core/harness/
├── tool_loop.py   LLM ⇄ tools loop used by BaseAgent.generate_with_tools
├── trace.py       RunTrace: per-run LLM/tool telemetry via contextvars
├── mock_llm.py    offline scripted provider "mock" for tests & dry runs
└── cli.py         run an agent or a full deal from the command line
```

### Execution path

```
Agent.run()
  ├─ self.generate_with_tools(prompt, system)      # tool-using turns
  │     └─ ToolLoop.run ──► LLMGateway.call ──► pooled client
  │            └─ ToolRouter.execute (concurrent, allowlisted, timed out)
  └─ self.llm_generate(prompt, system)             # plain turns
        └─ LLMGateway.call ──► pooled client

LLMGateway.call:
  availability check (health TTL / API key) → rate limit → cache →
  run budget → per-provider semaphore → retry/backoff → fallback chain →
  trace record (provider-reported tokens when available)
```

### Running agents (from `backend/`)

```bash
# list agents
python -m app.core.harness.cli list

# one agent, fully offline
python -m app.core.harness.cli --provider mock agent financial_analyst "Analyze Acme Corp"

# one agent on a real provider, with the structured (issue-tree) flow
python -m app.core.harness.cli --provider gemini agent market_researcher \
    "Market for EV chargers" --structured --context '{"target_company": "ChargePoint"}'

# the full deal workflow, saving the call-level trace
python -m app.core.harness.cli --provider mock --trace-out trace.json deal --target "Acme Corp"

# cap the run: at most 40 LLM calls / 300k tokens
python -m app.core.harness.cli --max-llm-calls 40 --max-tokens 300000 deal --target "Acme Corp"
```

The result goes to stdout as JSON and the trace summary goes to stderr. Omit
`--provider` to use the normal routing table. Add `-v` for debug logs.

### Tracing

Every deal run through `DealOrchestrator.run_deal` is traced automatically:

- `final_state["harness_trace"]`: summary (LLM calls, errors, cache hits,
  fallbacks, estimated tokens, tool calls/failures/dedup hits, per-agent
  breakdown). It is also returned by `POST /api/v1/deals/{id}/run`.
- `GET /api/v1/harness/traces`: summaries of the last 50 runs, including
  runs still in progress (`running: true`).
- `GET /api/v1/harness/traces/{deal_id}`: full call-level log.

To trace anything else:

```python
from app.core.harness import RunBudget, start_trace, agent_scope

with start_trace("my-run", budget=RunBudget(max_llm_calls=20)) as trace, \
        agent_scope("financial_analyst"):
    await agent.run(task, context)
print(trace.summary())
```

### Testing with the mock provider

```python
from app.core.harness.mock_llm import install_mock_provider, route_all_agents_to

mock = install_mock_provider()
route_all_agents_to("mock")
mock.tool_call("financial_calculator", calculation_type="multiple",
               inputs={"revenue": 10, "multiple": 3})
mock.queue({"content": '{"summary": "ok"}'})
# ... run an agent; inspect mock.calls for the prompts it received
```

Run the harness suite (from `backend/`):

```bash
python -m pytest tests/harness -q
```

### Tuning knobs

| Setting | Where | Default |
|---|---|---|
| Tool rounds per turn | `generate_with_tools(max_tool_rounds=)` | 3 |
| Tool timeout / result truncation | `ToolLoopConfig(tool_timeout_s, max_result_chars)` | 45 s / 4 000 chars |
| Providers using prompt-based (ReAct) tools | `tool_loop.REACT_PROVIDERS` | ollama, lmstudio, mistral |
| Concurrency per provider | `llm_gateway.DEFAULT_PROVIDER_CONCURRENCY` | 2 local / 8 cloud |
| Local health cache | `model_router.HEALTH_TTL_SECONDS` | 30 s |
| Network retries | `llm_gateway.MAX_NETWORK_RETRIES` | 2 |
| Graph step limit | workflow config `recursion_limit` | 60 |
| Per-run spend cap | workflow config `run_budget` / `run_deal(budget=)` | 200 LLM calls |
| Decision thresholds & gates | workflow config `decision_policy` | see `DecisionPolicy` |
| Analysis-agent retries before degrading | workflow config `max_agent_retries` | 1 |
| API key | env `DEALFORGE_API_KEY` | unset (open) |
| LLM requests per client per minute | env `DEALFORGE_LLM_RPM` | 30 |
| Max prompt length | env `DEALFORGE_MAX_PROMPT_CHARS` | 8000 |
| Reuse screening market output | workflow config `reuse_screening_market_output` | True |
| JSON repair | `generate_with_tools(expect_json=)` | True |
| Add a provider | `app.core.llm.register_llm_client(name, factory)` | — |
