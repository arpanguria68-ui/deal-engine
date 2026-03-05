"""
OFAS Supervisor Agent — Mission Control

Orchestrates the end-to-end OFAS workflow using RACI-based task delegation.
Creates mission plans, assigns tasks to specialized agents, enforces
quality gates, and routes issues back to responsible agents for resolution.

This agent is ACCOUNTABLE for every task in the mission.
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

from app.agents.base import BaseAgent, AgentOutput
from app.orchestrator.state import (
    OFASMissionState,
    OFASTask,
    OFASIssue,
    create_ofas_mission,
    create_ofas_task,
    create_ofas_issue,
    get_ready_tasks,
    has_blocking_issues,
)

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════
#  OFAS Standard Mission Templates
# ═══════════════════════════════════════════════════════════

DEAL_TYPE_TEMPLATES = {
    "standard_corporate": {
        "description": "Standard corporate acquisition / equity research",
        "tasks": [
            {
                "id": "data_ingestion",
                "name": "Data Ingestion & RAG Index",
                "responsible": ["financial_analyst"],
                "consulted": ["market_researcher"],
                "dependencies": [],
            },
            {
                "id": "model_build",
                "name": "Build 3-Statement + DCF Model",
                "responsible": ["dcf_lbo_architect"],
                "consulted": ["financial_analyst"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "valuation_comps",
                "name": "Comparable Companies & Valuation",
                "responsible": ["valuation_agent"],
                "consulted": ["dcf_lbo_architect"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "dd_risks",
                "name": "Due Diligence & Risk Assessment",
                "responsible": ["due_diligence_agent", "risk_assessor"],
                "consulted": ["legal_advisor"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "report_generation",
                "name": "IC Memo & Report Generation",
                "responsible": ["investment_memo_agent"],
                "consulted": [
                    "dcf_lbo_architect",
                    "valuation_agent",
                    "due_diligence_agent",
                ],
                "dependencies": ["model_build", "valuation_comps", "dd_risks"],
            },
            {
                "id": "compliance_review",
                "name": "Compliance & QA Review",
                "responsible": ["compliance_agent"],
                "consulted": ["investment_memo_agent", "dcf_lbo_architect"],
                "dependencies": ["report_generation", "model_build"],
            },
        ],
    },
    "ma_acquisition": {
        "description": "M&A acquisition with accretion/dilution",
        "tasks": [
            {
                "id": "data_ingestion",
                "name": "Data Ingestion (Acquirer + Target)",
                "responsible": ["financial_analyst"],
                "consulted": [],
                "dependencies": [],
            },
            {
                "id": "model_build",
                "name": "Build 3-Statement + Accretion/Dilution Model",
                "responsible": ["dcf_lbo_architect"],
                "consulted": ["financial_analyst"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "valuation_comps",
                "name": "Comps & Transaction Precedents",
                "responsible": ["valuation_agent"],
                "consulted": ["dcf_lbo_architect"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "dd_risks",
                "name": "M&A Due Diligence & Synergy Analysis",
                "responsible": ["due_diligence_agent", "risk_assessor"],
                "consulted": ["legal_advisor"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "report_generation",
                "name": "IC Memo with M&A Structure",
                "responsible": ["investment_memo_agent"],
                "consulted": [
                    "dcf_lbo_architect",
                    "valuation_agent",
                    "due_diligence_agent",
                ],
                "dependencies": ["model_build", "valuation_comps", "dd_risks"],
            },
            {
                "id": "compliance_review",
                "name": "Compliance & QA Review",
                "responsible": ["compliance_agent"],
                "consulted": ["investment_memo_agent"],
                "dependencies": ["report_generation"],
            },
        ],
    },
    "pe_lbo": {
        "description": "Private Equity LBO analysis",
        "tasks": [
            {
                "id": "data_ingestion",
                "name": "Data Ingestion & Financial Extraction",
                "responsible": ["financial_analyst"],
                "consulted": [],
                "dependencies": [],
            },
            {
                "id": "model_build",
                "name": "Build LBO + Cap Table Model",
                "responsible": ["dcf_lbo_architect"],
                "consulted": ["financial_analyst"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "valuation_comps",
                "name": "LBO Comps & Returns Analysis",
                "responsible": ["valuation_agent"],
                "consulted": ["dcf_lbo_architect"],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "dd_risks",
                "name": "Operational DD & Value Creation Levers",
                "responsible": ["due_diligence_agent", "risk_assessor"],
                "consulted": [],
                "dependencies": ["data_ingestion"],
            },
            {
                "id": "report_generation",
                "name": "IC Memo with Returns Analysis",
                "responsible": ["investment_memo_agent"],
                "consulted": [
                    "dcf_lbo_architect",
                    "valuation_agent",
                    "due_diligence_agent",
                ],
                "dependencies": ["model_build", "valuation_comps", "dd_risks"],
            },
            {
                "id": "compliance_review",
                "name": "Compliance & QA Review",
                "responsible": ["compliance_agent"],
                "consulted": ["investment_memo_agent"],
                "dependencies": ["report_generation"],
            },
        ],
    },
}

MAX_RETRY_CYCLES = 3


class OFASSupervisorAgent(BaseAgent):
    """
    OFAS Mission Control — the Supervisor agent.

    Accountable for every task in the mission. Creates RACI-based task plans,
    routes work to specialized agents, enforces quality gates, and manages
    the feedback loop when issues are detected.
    """

    name = "ofas_supervisor"
    description = (
        "OFAS Mission Control: orchestrates multi-agent financial analysis "
        "with RACI delegation, quality gates, and compliance enforcement."
    )

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Main entry point — Plan a mission or execute a specific supervisory action.

        Supported actions (via context["action"]):
        - "plan_mission": Create a RACI task plan for a deal
        - "get_status": Return current mission status
        - "route_issue": Route an issue to the responsible agent
        - "quality_gate": Run quality checks on a completed task
        """
        context = context or {}
        action = context.get("action", "plan_mission")

        try:
            if action == "plan_mission":
                return await self._plan_mission(task, context)
            elif action == "get_status":
                return await self._get_mission_status(context)
            elif action == "route_issue":
                return await self._route_issue(context)
            elif action == "quality_gate":
                return await self._run_quality_gate(context)
            else:
                return AgentOutput(
                    success=False,
                    data={"error": f"Unknown action: {action}"},
                    reasoning=f"Unsupported supervisor action: {action}",
                    confidence=0.0,
                )
        except Exception as e:
            self.logger.error("Supervisor error", action=action, error=str(e))
            return AgentOutput(
                success=False,
                data={"error": str(e)},
                reasoning=f"Supervisor failed: {str(e)}",
                confidence=0.0,
            )

    async def _plan_mission(self, objective: str, context: Dict) -> AgentOutput:
        """Create a RACI-based task plan for a deal"""

        ticker = context.get("ticker", "UNKNOWN")
        deal_type = context.get("deal_type", "standard_corporate")
        constraints = context.get("constraints", [])

        # Get template for the deal type
        template = DEAL_TYPE_TEMPLATES.get(deal_type)
        if not template:
            return AgentOutput(
                success=False,
                data={"error": f"Unknown deal type: {deal_type}"},
                reasoning=f"No template for deal type '{deal_type}'",
                confidence=0.0,
            )

        # Create mission state
        mission = create_ofas_mission(
            deal_id=context.get(
                "deal_id",
                f"ofas_{ticker}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            ),
            ticker=ticker,
            objective=objective,
            constraints=constraints,
        )

        # Build task list from template
        all_agents = set()
        for task_def in template["tasks"]:
            task = create_ofas_task(
                task_id=task_def["id"],
                name=task_def["name"],
                responsible=task_def["responsible"],
                consulted=task_def.get("consulted", []),
                dependencies=task_def.get("dependencies", []),
            )
            mission["tasks"].append(task)
            all_agents.update(task_def["responsible"])

        mission["mission_status"] = "in_progress"

        self.logger.info(
            "Mission planned",
            ticker=ticker,
            deal_type=deal_type,
            task_count=len(mission["tasks"]),
            agents=list(all_agents),
        )

        return AgentOutput(
            success=True,
            data={
                "mission": mission,
                "deal_type": deal_type,
                "template_description": template["description"],
                "task_count": len(mission["tasks"]),
                "agents_involved": sorted(all_agents),
                "ready_tasks": [t["id"] for t in get_ready_tasks(mission)],
            },
            reasoning=(
                f"Created {deal_type} mission for {ticker} with "
                f"{len(mission['tasks'])} tasks across {len(all_agents)} agents. "
                f"Ready to start: {[t['id'] for t in get_ready_tasks(mission)]}"
            ),
            confidence=0.95,
        )

    async def _get_mission_status(self, context: Dict) -> AgentOutput:
        """Return current mission status summary"""
        mission = context.get("mission")
        if not mission:
            return AgentOutput(
                success=False,
                data={"error": "No mission provided"},
                reasoning="Cannot get status without a mission state",
                confidence=0.0,
            )

        tasks_by_status = {}
        for task in mission.get("tasks", []):
            status = task.get("status", "pending")
            tasks_by_status.setdefault(status, []).append(task["id"])

        all_issues = []
        for task in mission.get("tasks", []):
            for issue in task.get("issues", []):
                all_issues.append({**issue, "task_id": task["id"]})

        error_issues = [i for i in all_issues if i.get("severity") == "error"]
        warn_issues = [i for i in all_issues if i.get("severity") == "warn"]

        return AgentOutput(
            success=True,
            data={
                "mission_status": mission.get("mission_status", "unknown"),
                "tasks_by_status": tasks_by_status,
                "total_tasks": len(mission.get("tasks", [])),
                "completed_tasks": len(tasks_by_status.get("done", [])),
                "blocked_tasks": len(tasks_by_status.get("blocked", [])),
                "error_count": len(error_issues),
                "warning_count": len(warn_issues),
                "ready_tasks": [t["id"] for t in get_ready_tasks(mission)],
                "artifacts": mission.get("artifacts", {}),
                "quality": mission.get("quality", {}),
            },
            reasoning=f"Mission status: {mission.get('mission_status', 'unknown')}",
            confidence=1.0,
        )

    async def _route_issue(self, context: Dict) -> AgentOutput:
        """Route an issue to the responsible agent for resolution"""
        mission = context.get("mission")
        issue_data = context.get("issue", {})
        task_id = issue_data.get("task_id", "")

        if not mission or not task_id:
            return AgentOutput(
                success=False,
                data={"error": "Mission and task_id required"},
                reasoning="Cannot route without mission state and task_id",
                confidence=0.0,
            )

        # Find the task
        target_task = None
        for task in mission.get("tasks", []):
            if task["id"] == task_id:
                target_task = task
                break

        if not target_task:
            return AgentOutput(
                success=False,
                data={"error": f"Task '{task_id}' not found"},
                reasoning=f"Task {task_id} not in mission",
                confidence=0.0,
            )

        # Check retry limit
        if target_task.get("retry_count", 0) >= MAX_RETRY_CYCLES:
            return AgentOutput(
                success=False,
                data={
                    "action": "escalate_to_human",
                    "task_id": task_id,
                    "retries_exhausted": True,
                    "issue": issue_data,
                },
                reasoning=(
                    f"Task '{task_id}' has exceeded max retry cycles ({MAX_RETRY_CYCLES}). "
                    f"Escalating to human review."
                ),
                confidence=1.0,
            )

        # Create the issue and attach to task
        issue = create_ofas_issue(
            msg=issue_data.get("msg", "Unknown issue"),
            owner=issue_data.get("owner", target_task["raci"]["R"][0]),
            severity=issue_data.get("severity", "warn"),
            task_id=task_id,
        )

        target_task.setdefault("issues", []).append(issue)
        target_task["retry_count"] = target_task.get("retry_count", 0) + 1

        # Set task status based on severity
        if issue["severity"] == "error":
            target_task["status"] = "blocked"
        elif issue["severity"] == "warn":
            target_task["status"] = "needs_review"

        return AgentOutput(
            success=True,
            data={
                "issue_routed": True,
                "task_id": task_id,
                "routed_to": issue["owner"],
                "severity": issue["severity"],
                "retry_count": target_task["retry_count"],
                "task_status": target_task["status"],
            },
            reasoning=(
                f"Issue routed to {issue['owner']} for task '{task_id}' "
                f"(severity: {issue['severity']}, retry: {target_task['retry_count']}/{MAX_RETRY_CYCLES})"
            ),
            confidence=0.9,
        )

    async def _run_quality_gate(self, context: Dict) -> AgentOutput:
        """Run quality checks on a completed task"""
        mission = context.get("mission")
        task_id = context.get("task_id", "")

        if not mission or not task_id:
            return AgentOutput(
                success=False,
                data={"error": "Mission and task_id required"},
                reasoning="Cannot run quality gate without mission and task_id",
                confidence=0.0,
            )

        target_task = None
        for task in mission.get("tasks", []):
            if task["id"] == task_id:
                target_task = task
                break

        if not target_task:
            return AgentOutput(
                success=False,
                data={"error": f"Task '{task_id}' not found"},
                reasoning=f"Task {task_id} not in mission",
                confidence=0.0,
            )

        outputs = target_task.get("outputs", {}) or {}
        checks = {}
        issues = []

        # Quality checks based on task type
        if task_id == "model_build":
            checks["has_model_path"] = bool(outputs.get("model_path"))
            checks["has_summary"] = bool(outputs.get("summary"))
            checks["balance_sheet_check"] = outputs.get("checks", {}).get(
                "balance_sheet_balanced", False
            )
            checks["cash_reconciles"] = outputs.get("checks", {}).get(
                "cash_reconciles", False
            )

            if not checks["balance_sheet_check"]:
                issues.append(
                    create_ofas_issue(
                        msg="Balance sheet does not balance",
                        owner="dcf_lbo_architect",
                        severity="error",
                        task_id=task_id,
                    )
                )
            if not checks["cash_reconciles"]:
                issues.append(
                    create_ofas_issue(
                        msg="Cash flow does not reconcile",
                        owner="dcf_lbo_architect",
                        severity="error",
                        task_id=task_id,
                    )
                )

        elif task_id == "report_generation":
            checks["has_memo_path"] = bool(outputs.get("memo_path"))
            checks["has_citations"] = outputs.get("citation_count", 0) > 0
            citation_coverage = outputs.get("citation_coverage", 0.0)
            checks["citation_coverage_ok"] = citation_coverage >= 0.9

            if not checks["has_citations"]:
                issues.append(
                    create_ofas_issue(
                        msg="Report has no citations",
                        owner="investment_memo_agent",
                        severity="error",
                        task_id=task_id,
                    )
                )
            if not checks["citation_coverage_ok"]:
                issues.append(
                    create_ofas_issue(
                        msg=f"Citation coverage ({citation_coverage:.0%}) below 90% threshold",
                        owner="investment_memo_agent",
                        severity="warn",
                        task_id=task_id,
                    )
                )

        # General checks
        checks["has_outputs"] = bool(outputs)
        checks["no_errors"] = len([i for i in issues if i["severity"] == "error"]) == 0

        passed = all(checks.values())

        return AgentOutput(
            success=passed,
            data={
                "task_id": task_id,
                "passed": passed,
                "checks": checks,
                "issues": issues,
                "issues_count": len(issues),
            },
            reasoning=(
                f"Quality gate {'PASSED' if passed else 'FAILED'} for task '{task_id}'. "
                f"Checks: {sum(checks.values())}/{len(checks)} passed. "
                f"Issues: {len(issues)}"
            ),
            confidence=0.95 if passed else 0.5,
        )
