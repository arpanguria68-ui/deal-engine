"""Task Management System — SQLAlchemy models + CRUD for Todo Lists"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid
import json
import structlog

logger = structlog.get_logger()


# ─── Enums ───────────────────────────────────────────────
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ─── Data Classes (no SQLAlchemy dependency) ─────────────
@dataclass
class TodoItem:
    """A single task in a todo list."""

    id: str = ""
    list_id: str = ""
    title: str = ""
    description: str = ""
    assigned_agent: str = ""
    status: str = "pending"
    priority: str = "medium"
    order: int = 0
    result: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        self.updated_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "list_id": self.list_id,
            "title": self.title,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "priority": self.priority,
            "order": self.order,
            "result": self.result,
            "depends_on": self.depends_on,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class TodoList:
    """A collection of tasks for a deal analysis."""

    id: str = ""
    deal_id: str = ""
    title: str = ""
    description: str = ""
    status: str = "draft"  # draft → approved → in_progress → completed
    items: List[TodoItem] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "deal_id": self.deal_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "items": [i.to_dict() for i in self.items],
            "summary": {
                "total": len(self.items),
                "pending": sum(1 for i in self.items if i.status == "pending"),
                "in_progress": sum(1 for i in self.items if i.status == "in_progress"),
                "done": sum(1 for i in self.items if i.status == "done"),
            },
        }


# ─── Task Manager ────────────────────────────────────────
# Agent → capability mapping for auto-assignment
AGENT_CAPABILITIES = {
    "financial_analyst": {
        "keywords": [
            "financial analysis",
            "revenue",
            "income statement",
            "cash flow",
            "ratios",
            "margins",
        ],
        "description": "Financial statement analysis, ratio calculations, revenue projections",
    },
    "valuation_agent": {
        "keywords": [
            "valuation",
            "dcf",
            "multiples",
            "comps",
            "comparable",
            "enterprise value",
        ],
        "description": "DCF, comparable companies, precedent transactions valuation",
    },
    "dcf_lbo_architect": {
        "keywords": [
            "lbo",
            "leveraged buyout",
            "debt waterfall",
            "dcf model",
            "financial spreading",
        ],
        "description": "LBO modeling, debt waterfalls, detailed DCF construction",
    },
    "legal_advisor": {
        "keywords": [
            "legal",
            "contract",
            "clause",
            "liability",
            "regulatory",
            "governance",
        ],
        "description": "Legal risk assessment, contract review, regulatory compliance",
    },
    "compliance_agent": {
        "keywords": ["compliance", "regulation", "aml", "kyc", "sanctions", "audit"],
        "description": "Regulatory compliance screening, policy verification",
    },
    "risk_assessor": {
        "keywords": [
            "risk",
            "threat",
            "scenario",
            "sensitivity",
            "stress test",
            "downside",
        ],
        "description": "Risk identification, scenario analysis, sensitivity testing",
    },
    "market_risk_agent": {
        "keywords": [
            "market risk",
            "interest rate",
            "currency",
            "fx",
            "commodity",
            "volatility",
        ],
        "description": "Market risk factors — FX, interest rates, commodity exposure",
    },
    "market_researcher": {
        "keywords": [
            "market",
            "industry",
            "competitor",
            "tam",
            "sam",
            "trend",
            "landscape",
        ],
        "description": "Market sizing, competitive analysis, industry trends",
    },
    "prospectus_agent": {
        "keywords": [
            "s-1",
            "10-k",
            "filing",
            "sec",
            "prospectus",
            "data room",
            "document",
        ],
        "description": "S-1/10-K processing, data room document extraction",
    },
    "due_diligence_agent": {
        "keywords": ["due diligence", "cim", "peer", "thesis", "screening"],
        "description": "Commercial due diligence, peer identification, deal screening",
    },
    "investment_memo_agent": {
        "keywords": [
            "memo",
            "report",
            "presentation",
            "executive summary",
            "recommendation",
        ],
        "description": "Investment memo drafting, executive summary, charts",
    },
    "treasury_agent": {
        "keywords": ["treasury", "cash", "liquidity", "forecast", "fpa", "tax"],
        "description": "Cash positioning, FP&A forecasting, tax compliance",
    },
    "debate_moderator": {
        "keywords": ["debate", "bull", "bear", "perspective", "argument"],
        "description": "Coordinates bull vs bear debate between agents",
    },
    "scoring_agent": {
        "keywords": ["score", "rating", "grade", "final", "aggregate"],
        "description": "Final deal scoring and aggregation",
    },
}


class TaskManager:
    """Manages todo lists and task execution for deal analysis."""

    def __init__(self):
        self._lists: Dict[str, TodoList] = (
            {}
        )  # In-memory store (persisted via Redis/DB later)
        self.logger = structlog.get_logger()

    # ── CRUD ──────────────────────────────────────────────
    def create_todo_list(
        self,
        deal_id: str,
        title: str,
        items: List[Dict[str, Any]],
        description: str = "",
    ) -> TodoList:
        """Create a new todo list with tasks."""
        todo = TodoList(deal_id=deal_id, title=title, description=description)
        for i, item_data in enumerate(items):
            todo.items.append(
                TodoItem(
                    list_id=todo.id,
                    title=item_data.get("title", f"Task {i+1}"),
                    description=item_data.get("description", ""),
                    assigned_agent=item_data.get(
                        "assigned_agent", self._auto_assign(item_data.get("title", ""))
                    ),
                    priority=item_data.get("priority", "medium"),
                    order=i,
                    depends_on=item_data.get("depends_on", []),
                )
            )
        self._lists[todo.id] = todo
        self.logger.info(
            "todo_list_created", list_id=todo.id, deal_id=deal_id, tasks=len(todo.items)
        )
        return todo

    def get_todo_list(self, list_id: str) -> Optional[TodoList]:
        return self._lists.get(list_id)

    def get_lists_for_deal(self, deal_id: str) -> List[TodoList]:
        return [tl for tl in self._lists.values() if tl.deal_id == deal_id]

    def update_task(
        self, list_id: str, task_id: str, updates: Dict[str, Any]
    ) -> Optional[TodoItem]:
        """Update a specific task's fields."""
        todo = self._lists.get(list_id)
        if not todo:
            return None
        for item in todo.items:
            if item.id == task_id:
                for key, value in updates.items():
                    if hasattr(item, key) and key not in (
                        "id",
                        "list_id",
                        "created_at",
                    ):
                        setattr(item, key, value)
                item.updated_at = datetime.utcnow().isoformat()
                return item
        return None

    def delete_task(self, list_id: str, task_id: str) -> bool:
        """Remove a task from a list."""
        todo = self._lists.get(list_id)
        if not todo:
            return False
        original_len = len(todo.items)
        todo.items = [i for i in todo.items if i.id != task_id]
        return len(todo.items) < original_len

    def add_task(self, list_id: str, item_data: Dict[str, Any]) -> Optional[TodoItem]:
        """Add a new task to an existing list."""
        todo = self._lists.get(list_id)
        if not todo:
            return None
        item = TodoItem(
            list_id=list_id,
            title=item_data.get("title", ""),
            description=item_data.get("description", ""),
            assigned_agent=item_data.get(
                "assigned_agent", self._auto_assign(item_data.get("title", ""))
            ),
            priority=item_data.get("priority", "medium"),
            order=len(todo.items),
        )
        todo.items.append(item)
        return item

    def approve_list(self, list_id: str) -> Optional[TodoList]:
        """Mark a todo list as approved (ready for execution)."""
        todo = self._lists.get(list_id)
        if todo:
            todo.status = "approved"
        return todo

    def reorder_tasks(self, list_id: str, task_ids: List[str]) -> bool:
        """Reorder tasks based on provided ID sequence."""
        todo = self._lists.get(list_id)
        if not todo:
            return False
        id_to_item = {i.id: i for i in todo.items}
        new_items = []
        for idx, tid in enumerate(task_ids):
            if tid in id_to_item:
                id_to_item[tid].order = idx
                new_items.append(id_to_item[tid])
        # Add any items not in the reorder list at the end
        for item in todo.items:
            if item.id not in task_ids:
                item.order = len(new_items)
                new_items.append(item)
        todo.items = new_items
        return True

    # ── Auto-assignment ───────────────────────────────────
    def _auto_assign(self, task_title: str) -> str:
        """Auto-assign an agent based on task title keywords."""
        title_lower = task_title.lower()
        best_agent = "financial_analyst"
        best_score = 0
        for agent, caps in AGENT_CAPABILITIES.items():
            score = sum(1 for kw in caps["keywords"] if kw in title_lower)
            if score > best_score:
                best_score = score
                best_agent = agent
        return best_agent

    # ── Execution helpers ─────────────────────────────────
    def get_next_tasks(self, list_id: str) -> List[TodoItem]:
        """Get tasks that are ready to execute (pending + dependencies met)."""
        todo = self._lists.get(list_id)
        if not todo:
            return []
        done_ids = {i.id for i in todo.items if i.status == "done"}
        ready = []
        for item in sorted(todo.items, key=lambda x: x.order):
            if item.status == "pending":
                if all(dep in done_ids for dep in item.depends_on):
                    ready.append(item)
        return ready

    def mark_task_result(
        self, list_id: str, task_id: str, result: Dict[str, Any]
    ) -> None:
        """Store the result of an executed task."""
        self.update_task(list_id, task_id, {"status": "done", "result": result})
        # Check if all tasks are done
        todo = self._lists.get(list_id)
        if todo and all(i.status == "done" for i in todo.items):
            todo.status = "completed"


# ── Singleton ─────────────────────────────────────────────
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
