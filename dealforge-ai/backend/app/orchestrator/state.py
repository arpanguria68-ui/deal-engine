"""LangGraph State Definitions for DealForge"""

from typing import Dict, Any, List, Optional, TypedDict, Literal
from datetime import datetime
from enum import Enum


# ═══════════════════════════════════════════════════════════
#  OFAS — RACI-Based Task & Issue Models
# ═══════════════════════════════════════════════════════════


class OFASIssue(TypedDict, total=False):
    """An issue logged by an agent during task execution"""

    msg: str
    owner: str  # agent name responsible for fixing
    severity: str  # "info", "warn", "error"
    task_id: str
    timestamp: str


class OFASTask(TypedDict, total=False):
    """A task in the OFAS mission with RACI assignments"""

    id: str
    name: str
    raci: Dict[str, List[str]]  # {"R": [...], "A": [...], "C": [...], "I": [...]}
    status: str  # "pending", "running", "done", "blocked", "needs_review"
    outputs: Optional[Dict[str, Any]]
    issues: List[OFASIssue]
    dependencies: List[str]  # task IDs that must complete first
    retry_count: int


class OFASMissionState(TypedDict, total=False):
    """
    State for an OFAS mission — runs alongside the existing DealState.

    This is a separate state graph for the OFAS workflow, allowing
    the Supervisor to orchestrate tasks with RACI delegation while
    the existing DealOrchestrator continues to work for standard flows.
    """

    # Mission-level
    deal_id: str
    ticker: str
    objective: str
    constraints: List[str]
    mission_status: str  # "planning", "in_progress", "review", "ready_for_client"

    # Task tracking
    tasks: List[OFASTask]

    # Artifacts produced
    artifacts: Dict[str, str]  # {"model_path": "...", "memo_path": "...", ...}

    # Quality metrics
    quality: Dict[str, float]  # {"model_accuracy": 0.98, "citation_coverage": 1.0}

    # RAG context
    rag_index_path: str

    # Financial data cache
    financial_data: Optional[Dict[str, Any]]

    # Metadata
    created_at: str
    updated_at: str
    version: int


def create_ofas_mission(
    deal_id: str,
    ticker: str,
    objective: str,
    constraints: Optional[List[str]] = None,
) -> "OFASMissionState":
    """Create initial state for an OFAS mission"""
    now = datetime.utcnow().isoformat()

    return {
        "deal_id": deal_id,
        "ticker": ticker,
        "objective": objective,
        "constraints": constraints or [],
        "mission_status": "planning",
        "tasks": [],
        "artifacts": {},
        "quality": {},
        "rag_index_path": "",
        "financial_data": None,
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }


def create_ofas_task(
    task_id: str,
    name: str,
    responsible: List[str],
    accountable: str = "ofas_supervisor",
    consulted: Optional[List[str]] = None,
    informed: Optional[List[str]] = None,
    dependencies: Optional[List[str]] = None,
) -> OFASTask:
    """Create an OFAS task with RACI assignments"""
    return {
        "id": task_id,
        "name": name,
        "raci": {
            "R": responsible,
            "A": [accountable],
            "C": consulted or [],
            "I": informed or [],
        },
        "status": "pending",
        "outputs": None,
        "issues": [],
        "dependencies": dependencies or [],
        "retry_count": 0,
    }


def create_ofas_issue(
    msg: str,
    owner: str,
    severity: str = "info",
    task_id: str = "",
) -> OFASIssue:
    """Create an OFAS issue"""
    return {
        "msg": msg,
        "owner": owner,
        "severity": severity,
        "task_id": task_id,
        "timestamp": datetime.utcnow().isoformat(),
    }


def get_ready_tasks(mission: OFASMissionState) -> List[OFASTask]:
    """Get tasks whose dependencies are all 'done' and status is 'pending'"""
    done_ids = {t["id"] for t in mission["tasks"] if t["status"] == "done"}
    ready = []
    for task in mission["tasks"]:
        if task["status"] != "pending":
            continue
        deps = set(task.get("dependencies", []))
        if deps.issubset(done_ids):
            ready.append(task)
    return ready


def has_blocking_issues(mission: OFASMissionState) -> bool:
    """Check if any task has error-severity issues"""
    for task in mission["tasks"]:
        for issue in task.get("issues", []):
            if issue.get("severity") == "error":
                return True
    return False


class DealStage(str, Enum):
    """Deal workflow stages"""

    INIT = "init"
    SCREENING = "screening"
    VALUATION = "valuation"
    DUE_DILIGENCE = "due_diligence"
    DEBATE = "debate"
    RED_TEAM = "red_team"
    SCORING = "scoring"
    DECISION = "decision"
    COMPLETED = "completed"
    ERROR = "error"


class AgentState(str, Enum):
    """Individual agent states"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    WAITING = "waiting"


class DealState(TypedDict, total=False):
    """Main state for deal workflow"""

    # Deal identification
    deal_id: str
    deal_name: str

    # Workflow state
    current_stage: DealStage
    stage_history: List[str]

    # Agent outputs
    financial_output: Optional[Dict[str, Any]]
    legal_output: Optional[Dict[str, Any]]
    risk_output: Optional[Dict[str, Any]]
    market_output: Optional[Dict[str, Any]]
    debate_output: Optional[Dict[str, Any]]
    red_team_output: Optional[Dict[str, Any]]
    scoring_output: Optional[Dict[str, Any]]
    analyst_output: Optional[Dict[str, Any]]

    # MECE Issue Tree
    issue_tree: Optional[Dict[str, Any]]
    red_team_flags: Optional[List[Dict[str, Any]]]

    # Agent states
    agent_states: Dict[str, AgentState]

    # Context
    context: Dict[str, Any]
    documents: List[str]

    # Results
    final_recommendation: Optional[str]
    final_score: Optional[float]

    # Execution tracking
    started_at: str
    updated_at: str
    completed_at: Optional[str]

    # Error handling
    error_message: Optional[str]
    retry_count: int

    # Human intervention
    awaiting_decision: bool
    decision_request: Optional[Dict[str, Any]]


class WorkflowConfig(TypedDict, total=False):
    """Configuration for workflow execution"""

    # Execution settings
    max_iterations: int
    timeout_seconds: int
    parallel_execution: bool

    # Agent settings
    enabled_agents: List[str]
    agent_timeout_seconds: int

    # Reflection settings
    enable_reflection: bool
    reflection_threshold: float

    # Human-in-the-loop
    require_human_approval: bool
    approval_stages: List[str]

    # Scoring
    scoring_weights: Dict[str, float]
    min_deal_score: float


def create_initial_state(
    deal_id: str, deal_name: str, context: Dict[str, Any] = None
) -> DealState:
    """Create initial state for a new deal workflow"""
    now = datetime.utcnow().isoformat()

    return {
        "deal_id": deal_id,
        "deal_name": deal_name,
        "current_stage": DealStage.INIT,
        "stage_history": [DealStage.INIT],
        "financial_output": None,
        "legal_output": None,
        "risk_output": None,
        "market_output": None,
        "debate_output": None,
        "red_team_output": None,
        "scoring_output": None,
        "analyst_output": None,
        "issue_tree": None,
        "red_team_flags": [],
        "agent_states": {},
        "context": context or {},
        "documents": [],
        "final_recommendation": None,
        "final_score": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
        "error_message": None,
        "retry_count": 0,
        "awaiting_decision": False,
        "decision_request": None,
    }


def update_state(state: DealState, updates: Dict[str, Any]) -> DealState:
    """Update state with new values"""
    new_state = state.copy()
    new_state.update(updates)
    new_state["updated_at"] = datetime.utcnow().isoformat()
    return new_state


def add_stage_to_history(state: DealState, stage: str) -> DealState:
    """Add stage to history"""
    history = state.get("stage_history", [])
    history.append(stage)
    return update_state(state, {"stage_history": history})


def set_agent_state(
    state: DealState, agent_name: str, agent_state: AgentState
) -> DealState:
    """Set state for a specific agent"""
    agent_states = state.get("agent_states", {})
    agent_states[agent_name] = agent_state
    return update_state(state, {"agent_states": agent_states})


def get_agent_output(state: DealState, agent_type: str) -> Optional[Dict[str, Any]]:
    """Get output from a specific agent"""
    output_map = {
        "financial_analyst": state.get("financial_output"),
        "legal_advisor": state.get("legal_output"),
        "risk_assessor": state.get("risk_output"),
        "market_researcher": state.get("market_output"),
        "debate_moderator": state.get("debate_output"),
        "red_team": state.get("red_team_output"),
        "scoring_agent": state.get("scoring_output"),
        "business_analyst": state.get("analyst_output"),
    }
    return output_map.get(agent_type)


def all_agents_completed(state: DealState, required_agents: List[str]) -> bool:
    """Check if all required agents have completed"""
    agent_states = state.get("agent_states", {})

    for agent in required_agents:
        if agent_states.get(agent) != AgentState.COMPLETED:
            return False

    return True


def has_errors(state: DealState) -> bool:
    """Check if any agent has errored"""
    agent_states = state.get("agent_states", {})
    return any(state == AgentState.ERROR for state in agent_states.values())


def get_error_agents(state: DealState) -> List[str]:
    """Get list of agents that have errored"""
    agent_states = state.get("agent_states", {})
    return [name for name, state in agent_states.items() if state == AgentState.ERROR]
