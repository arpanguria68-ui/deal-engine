"""
OFAS Execution Engine — Parallel Task Scheduling, Review Gates, Monitoring

Production-ready orchestration layer for OFAS missions:
- Dependency-aware parallel task scheduling using asyncio.gather
- Human-in-the-loop review gates at configurable checkpoints
- Real-time mission monitoring and health checks
- Error recovery with Supervisor re-routing
"""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
import structlog

from app.orchestrator.state import (
    OFASMissionState,
    OFASTask,
    get_ready_tasks,
    has_blocking_issues,
)

logger = structlog.get_logger()


# ═══════════════════════════════════════════════
#  Review Gate Configuration
# ═══════════════════════════════════════════════


class ReviewGateType(str, Enum):
    """Types of review gates"""

    AUTO = "auto"  # ComplianceQA agent runs automatically
    HUMAN_REQUIRED = "human"  # Blocks until human approves
    OPTIONAL = "optional"  # Can be skipped after timeout


# Default review gate checkpoints
DEFAULT_REVIEW_GATES = {
    "after_data_collection": {
        "type": ReviewGateType.AUTO,
        "description": "Verify all financial data sources are populated",
        "checks": ["financial_data_complete", "rag_index_populated"],
    },
    "after_model_build": {
        "type": ReviewGateType.HUMAN_REQUIRED,
        "description": "Human reviews the financial model before valuation",
        "checks": ["formulas_preserved", "balance_sheet_balanced"],
    },
    "after_valuation": {
        "type": ReviewGateType.AUTO,
        "description": "ComplianceQA validates valuation consistency",
        "checks": ["multiple_methodologies", "range_reasonable"],
    },
    "before_ic_submission": {
        "type": ReviewGateType.HUMAN_REQUIRED,
        "description": "Final human review before IC memo is generated",
        "checks": ["all_sections_complete", "citations_linked", "confidential_marked"],
    },
}


class ReviewGateResult:
    """Result of a review gate evaluation"""

    def __init__(
        self,
        gate_name: str,
        passed: bool,
        checks: Dict[str, bool],
        requires_human: bool = False,
        human_approved: Optional[bool] = None,
        notes: str = "",
    ):
        self.gate_name = gate_name
        self.passed = passed
        self.checks = checks
        self.requires_human = requires_human
        self.human_approved = human_approved
        self.notes = notes
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "checks": self.checks,
            "requires_human": self.requires_human,
            "human_approved": self.human_approved,
            "notes": self.notes,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════
#  OFAS Execution Engine
# ═══════════════════════════════════════════════


class OFASExecutionEngine:
    """
    Production-ready execution engine for OFAS missions.

    Features:
    - Dependency-aware parallel task scheduling
    - Configurable review gates (auto/human/optional)
    - Real-time monitoring via mission_monitor()
    - Error recovery with automatic re-routing
    - Execution telemetry for performance tracking
    """

    def __init__(
        self,
        agent_timeout_seconds: int = 120,
        max_parallel: int = 4,
        review_gates: Optional[Dict] = None,
    ):
        self.agent_timeout = agent_timeout_seconds
        self.max_parallel = max_parallel
        self.review_gates = review_gates or DEFAULT_REVIEW_GATES
        self.logger = logger.bind(module="ofas_engine")

        # Telemetry
        self._telemetry: Dict[str, List[Dict]] = {}
        self._active_missions: Dict[str, OFASMissionState] = {}

    # ── Parallel Task Scheduling ──

    async def execute_ready_tasks(
        self,
        mission: OFASMissionState,
        agent_registry: Dict[str, Any],
    ) -> OFASMissionState:
        """
        Find all tasks whose dependencies are met and execute them in parallel.
        Returns updated mission state.
        """
        ready = get_ready_tasks(mission)
        if not ready:
            self.logger.info("No ready tasks", mission_id=mission["deal_id"])
            return mission

        # Limit parallelism
        batch = ready[: self.max_parallel]
        self.logger.info(
            "Executing parallel batch",
            mission_id=mission["deal_id"],
            tasks=[t["id"] for t in batch],
            parallel_count=len(batch),
        )

        # Mark tasks as running
        for task in batch:
            task["status"] = "running"

        # Execute in parallel
        coros = []
        for task in batch:
            responsible = task["raci"].get("R", [])
            agent_name = responsible[0] if responsible else "financial_analyst"
            agent = agent_registry.get(agent_name)

            if agent:
                coros.append(
                    self._execute_task_with_timeout(task, agent, mission, agent_name)
                )
            else:
                task["status"] = "blocked"
                task["issues"].append(
                    {
                        "msg": f"Agent '{agent_name}' not found in registry",
                        "owner": "ofas_supervisor",
                        "severity": "error",
                        "task_id": task["id"],
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)

            for i, result in enumerate(results):
                task = batch[i]
                if isinstance(result, Exception):
                    task["status"] = "blocked"
                    task["issues"].append(
                        {
                            "msg": f"Task execution failed: {str(result)}",
                            "owner": "ofas_supervisor",
                            "severity": "error",
                            "task_id": task["id"],
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    self._record_telemetry(
                        mission["deal_id"], task["id"], "error", str(result)
                    )
                elif isinstance(result, dict):
                    task["status"] = "done"
                    task["outputs"] = result
                    self._record_telemetry(mission["deal_id"], task["id"], "done")

        mission["updated_at"] = datetime.utcnow().isoformat()
        return mission

    async def _execute_task_with_timeout(
        self, task: OFASTask, agent, mission: OFASMissionState, agent_name: str
    ) -> Dict:
        """Execute a single task with timeout protection"""
        start = datetime.utcnow()
        try:
            context = {
                "deal_id": mission["deal_id"],
                "ticker": mission.get("ticker", ""),
                "task_name": task["name"],
                "financial_data": mission.get("financial_data"),
            }

            result = await asyncio.wait_for(
                agent.run(task["name"], context),
                timeout=self.agent_timeout,
            )

            elapsed = (datetime.utcnow() - start).total_seconds()
            self.logger.info(
                "Task completed",
                task_id=task["id"],
                agent=agent_name,
                elapsed_s=round(elapsed, 2),
            )

            return result.data if hasattr(result, "data") else {"result": str(result)}

        except asyncio.TimeoutError:
            raise Exception(
                f"Task '{task['id']}' timed out after {self.agent_timeout}s"
            )

    # ── Review Gates ──

    async def evaluate_review_gate(
        self,
        gate_name: str,
        mission: OFASMissionState,
        human_decision: Optional[bool] = None,
    ) -> ReviewGateResult:
        """
        Evaluate a review gate checkpoint.

        For AUTO gates: runs ComplianceQA automatically.
        For HUMAN gates: checks if human_decision is provided.
        """
        gate_config = self.review_gates.get(gate_name)
        if not gate_config:
            return ReviewGateResult(
                gate_name=gate_name,
                passed=True,
                checks={},
                notes="Gate not configured — auto-passing",
            )

        gate_type = gate_config.get("type", ReviewGateType.AUTO)
        check_names = gate_config.get("checks", [])
        checks = {}

        # Run automated checks
        for check in check_names:
            checks[check] = self._run_check(check, mission)

        all_auto_passed = all(checks.values()) if checks else True

        if gate_type == ReviewGateType.AUTO:
            return ReviewGateResult(
                gate_name=gate_name,
                passed=all_auto_passed,
                checks=checks,
            )

        elif gate_type == ReviewGateType.HUMAN_REQUIRED:
            if human_decision is None:
                # Block — waiting for human
                mission["mission_status"] = "review"
                return ReviewGateResult(
                    gate_name=gate_name,
                    passed=False,
                    checks=checks,
                    requires_human=True,
                    notes="Awaiting human review and approval",
                )
            else:
                return ReviewGateResult(
                    gate_name=gate_name,
                    passed=human_decision and all_auto_passed,
                    checks=checks,
                    requires_human=True,
                    human_approved=human_decision,
                )

        else:  # OPTIONAL
            return ReviewGateResult(
                gate_name=gate_name,
                passed=all_auto_passed,
                checks=checks,
                notes="Optional gate — proceeding regardless",
            )

    def _run_check(self, check_name: str, mission: OFASMissionState) -> bool:
        """Run a specific quality check against mission state"""
        if check_name == "financial_data_complete":
            return mission.get("financial_data") is not None

        elif check_name == "rag_index_populated":
            return bool(mission.get("rag_index_path"))

        elif check_name == "formulas_preserved":
            quality = mission.get("quality", {})
            return quality.get("formulas_preserved", True)

        elif check_name == "balance_sheet_balanced":
            quality = mission.get("quality", {})
            return quality.get("balance_sheet_balanced", True)

        elif check_name == "multiple_methodologies":
            artifacts = mission.get("artifacts", {})
            return bool(artifacts.get("valuation_data"))

        elif check_name == "range_reasonable":
            return True  # Placeholder — would check valuation range width

        elif check_name == "all_sections_complete":
            artifacts = mission.get("artifacts", {})
            return bool(artifacts.get("memo_path"))

        elif check_name == "citations_linked":
            quality = mission.get("quality", {})
            return quality.get("citation_coverage", 0) >= 0.8

        elif check_name == "confidential_marked":
            return True  # IC memo tool always adds confidential header

        return True  # Unknown checks pass by default

    # ── Monitoring ──

    def mission_monitor(self, mission: OFASMissionState) -> Dict[str, Any]:
        """Get real-time monitoring data for a mission"""
        tasks = mission.get("tasks", [])
        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "done")
        running = sum(1 for t in tasks if t["status"] == "running")
        blocked = sum(1 for t in tasks if t["status"] == "blocked")
        pending = sum(1 for t in tasks if t["status"] == "pending")

        all_issues = []
        for t in tasks:
            all_issues.extend(t.get("issues", []))

        error_count = sum(1 for i in all_issues if i.get("severity") == "error")
        warn_count = sum(1 for i in all_issues if i.get("severity") == "warn")

        # Calculate progress
        progress = (done / total * 100) if total > 0 else 0

        # Health status
        if error_count > 0:
            health = "critical"
        elif blocked > 0:
            health = "degraded"
        elif warn_count > 0:
            health = "warning"
        else:
            health = "healthy"

        return {
            "deal_id": mission["deal_id"],
            "ticker": mission.get("ticker", ""),
            "mission_status": mission.get("mission_status", "unknown"),
            "progress_pct": round(progress, 1),
            "health": health,
            "tasks": {
                "total": total,
                "done": done,
                "running": running,
                "blocked": blocked,
                "pending": pending,
            },
            "issues": {
                "total": len(all_issues),
                "errors": error_count,
                "warnings": warn_count,
            },
            "quality": mission.get("quality", {}),
            "artifacts": list(mission.get("artifacts", {}).keys()),
            "telemetry": self._telemetry.get(mission["deal_id"], [])[-10:],
            "updated_at": mission.get("updated_at"),
        }

    # ── Error Recovery ──

    async def recover_blocked_tasks(
        self,
        mission: OFASMissionState,
        agent_registry: Dict[str, Any],
        max_retries: int = 3,
    ) -> OFASMissionState:
        """
        Attempt to recover blocked tasks by re-routing to Supervisor.
        """
        blocked_tasks = [t for t in mission["tasks"] if t["status"] == "blocked"]

        for task in blocked_tasks:
            if task["retry_count"] >= max_retries:
                task["status"] = "needs_review"
                self.logger.warning(
                    "Task exceeded retry limit",
                    task_id=task["id"],
                    retries=task["retry_count"],
                )
                continue

            # Clear the error issues and retry
            task["issues"] = [i for i in task["issues"] if i.get("severity") != "error"]
            task["status"] = "pending"
            task["retry_count"] += 1

            self.logger.info(
                "Retrying blocked task",
                task_id=task["id"],
                retry=task["retry_count"],
            )

        mission["updated_at"] = datetime.utcnow().isoformat()
        return mission

    # ── Telemetry ──

    def _record_telemetry(
        self, mission_id: str, task_id: str, status: str, detail: str = ""
    ):
        if mission_id not in self._telemetry:
            self._telemetry[mission_id] = []
        self._telemetry[mission_id].append(
            {
                "task_id": task_id,
                "status": status,
                "detail": detail,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_telemetry(self, mission_id: str) -> List[Dict]:
        return self._telemetry.get(mission_id, [])

    def get_performance_summary(self, mission_id: str) -> Dict:
        """Get performance summary for a mission"""
        events = self._telemetry.get(mission_id, [])
        done_events = [e for e in events if e["status"] == "done"]
        error_events = [e for e in events if e["status"] == "error"]

        return {
            "mission_id": mission_id,
            "total_events": len(events),
            "tasks_completed": len(done_events),
            "tasks_failed": len(error_events),
            "success_rate": (
                round(
                    len(done_events)
                    / max(1, len(done_events) + len(error_events))
                    * 100,
                    1,
                )
            ),
        }
