# Agent Quality & Reliability Overhaul

This document tracks the initial implementation steps for epic **8ced8f91-7fdb-4ae3-a4a3-e24b35dfa403** (Enhancing AI Analyst Replication for PE Consulting).

## Goals

* Improve deterministic behaviour and replication of key analytical agents (especially `financial_analyst`).
* Introduce infrastructure to measure and record replication consistency across runs.
* Expand the existing quality store with replication metrics and expose evaluation helpers.
* Update test suite to cover replication and maintain new benchmarks.
* Default agent LLM calls to low temperature and deterministic settings wherever appropriate.

## Work completed so far

* Added `ReplicationEvaluator` utility in `app/core/quality/replication.py`.
* Extended `AgentQualityStore` with a new `replication_runs` table and helper methods.
* Created `BaseAgent.evaluate_replication` to exercise an agent multiple times.
* Modified `BaseAgent.generate_with_tools` and relevant agents to support temperature control and default to `0.0`.
* Added tests in `backend/tests/evals/test_replication.py` and updated `test_agents.py` for replication metrics.
* Updated benchmarks in `conftest.py`.
* Created this documentation file as the landing page for the epic.

## Next steps

1. Apply replication evaluation in CI and include metrics in reporting dashboards.
2. Instrument orchestration layer to automatically trigger replication checks for new deals or after model upgrades.
3. Provide a CLI command or API endpoint for manual replication audits.
4. Tune thresholds based on empirical data from PE consulting workflows.
5. Continue refining agent prompts and quality-store integration to drive down variance.
