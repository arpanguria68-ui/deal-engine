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

### Still open (recommendations, not changed here)

- **Market research runs twice per deal.** Screening runs `market_researcher` and parallel analysis runs it again with nearly the same task. Reuse the screening output on the first pass (re-run only when peer review sends feedback to it).
- **The issue tree costs an extra LLM call per agent**, and it dumps the whole context (including skill text) into the prompt as JSON. Consider making it opt-in per stage, or trimming the context first.
- **Tool rounds replay the whole prompt.** Clients take a single `prompt` string, so every round re-sends the original prompt plus all results. Moving to multi-turn `messages` would let provider prompt caching apply.
- **Token accounting is estimated** at 4 chars/token. Real `usage` from provider responses is ignored, so budgets and the usage dashboard are approximate.
- **SDK retries stack on gateway retries.** The OpenAI SDK retries twice by default, on top of the gateway's retries. Set `max_retries=0` on SDK clients once the gateway is the only retry layer.
- **Per-request agent construction in `main.py`.** `ProjectManagerAgent()` and `OFASSupervisorAgent()` are built per request. This is cheaper now with shared tools, but should still come from the registry.
- **Default routing is local-first** (LM Studio). Now it degrades gracefully, but in container deployments the default should be a cloud provider.
- **Repo hygiene.** Tracked log files (`backend/*.log`, `docs/legacy_dealforge/*.log`), `.bak` files, generated `.pptx` outputs, `*_out.txt`, and a 19 MB `Knowledge managerment/` folder with zips. `backend/data/agent_quality.db` is tracked and mutated by every run. Add these to `.gitignore` and untrack them.
- **Existing test suites are broken** independently of this change: `backend/tests/evals` is 20 failed / 3 passed on the original code (MCP signature mismatches, `NameError`s, imports), and most root `tests/` need live keys or fail on import. `app/main.py` is a 3 000-line monolith that would benefit from splitting into routers.

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
  per-provider semaphore → retry/backoff → fallback chain → trace record
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
```

The result goes to stdout as JSON and the trace summary goes to stderr. Omit
`--provider` to use the normal routing table. Add `-v` for debug logs.

### Tracing

Every deal run through `DealOrchestrator.run_deal` is traced automatically:

- `final_state["harness_trace"]`: summary (LLM calls, errors, cache hits,
  fallbacks, estimated tokens, tool calls/failures/dedup hits, per-agent
  breakdown). It is also returned by `POST /api/v1/deals/{id}/run`.
- `GET /api/v1/harness/traces`: summaries of the last 50 runs.
- `GET /api/v1/harness/traces/{deal_id}`: full call-level log.

To trace anything else:

```python
from app.core.harness import start_trace, agent_scope

with start_trace("my-run") as trace, agent_scope("financial_analyst"):
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
| Add a provider | `app.core.llm.register_llm_client(name, factory)` | — |
