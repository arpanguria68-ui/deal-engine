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
    ticker: str = ""
    company_name: str = ""
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
            "ticker": self.ticker,
            "company_name": self.company_name,
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
    "report_architect": {
        "keywords": ["report", "architect", "template", "branding", "layout", "pdf"],
        "description": "Selects report templates, configures branding, and organizes final output sections",
    },
    "data_curator": {
        "keywords": ["curate", "synthesize", "normalize", "conflicts", "data bible"],
        "description": "Synthesizes data from multiple sources, resolves conflicts, and queries PageIndex",
    },
    "complex_reasoning": {
        "keywords": ["reasoning", "chain of thought", "logic", "synthesis"],
        "description": "Applies deep Chain-of-Thought reasoning to curated data for strategic insights",
    },
    "advanced_financial_modeler": {
        "keywords": ["advanced model", "3-statement", "monte carlo", "scenario"],
        "description": "Builds 3-statement models, advanced scenarios, and Monte Carlo simulations",
    },
    "red_team": {
        "keywords": [
            "red team",
            "adversarial",
            "challenge",
            "stress test",
            "contrarian",
        ],
        "description": "Stress-tests assumptions with adversarial analysis and contrarian viewpoints",
    },
    "business_analyst": {
        "keywords": [
            "business model",
            "unit economics",
            "customer",
            "churn",
            "retention",
        ],
        "description": "Business model analysis, unit economics, strategic recommendations",
    },
    "compiler_agent": {
        "keywords": ["compile", "assemble", "final report", "output", "deliverable"],
        "description": "Compiles all agent outputs into cohesive final deliverables",
    },
    "esg_agent": {
        "keywords": [
            "esg",
            "environmental",
            "social",
            "governance",
            "sustainability",
            "carbon",
        ],
        "description": "ESG risk scoring, carbon footprint, supply chain risk analysis",
    },
    "integration_planner_agent": {
        "keywords": ["integration", "synergy", "roadmap", "merger integration", "pmi"],
        "description": "Post-merger integration planning, synergy tracking, and churn modeling",
    },
    "fpa_forecasting_agent": {
        "keywords": ["fpa", "forecast", "budget", "projection", "financial planning"],
        "description": "FP&A forecasting, budget modeling, and financial projections",
    },
    "tax_compliance_agent": {
        "keywords": ["tax", "compliance", "transfer pricing", "tax structure"],
        "description": "Tax compliance assessment and structure optimization",
    },
    "ai_tech_diligence_agent": {
        "keywords": [
            "ai",
            "machine learning",
            "tech stack",
            "data moat",
            "defensibility",
        ],
        "description": "AI/ML technology stack evaluation and defensibility scoring",
    },
}


class TaskManager:
    """Manages todo lists and task execution for deal analysis.

    Persists all data to SQLite via aiosqlite. An in-memory cache (_lists)
    is kept for fast reads; all writes are flushed to disk transactionally.
    """

    def __init__(self, db_path: str = None):
        import os
        from app.config import get_settings

        settings = get_settings()

        if not db_path:
            base = settings.DATA_DIR
            os.makedirs(base, exist_ok=True)
            self.db_path = os.path.join(base, "dealforge_tasks.db")
        else:
            self.db_path = db_path

        self._lists: Dict[str, TodoList] = {}  # Read-through cache
        self._initialized = False
        self.logger = structlog.get_logger()

    async def initialize(self):
        """Create tables if they don't exist and load all lists into cache."""
        import aiosqlite

        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS todo_lists (
                    id TEXT PRIMARY KEY,
                    deal_id TEXT NOT NULL,
                    ticker TEXT DEFAULT '',
                    company_name TEXT DEFAULT '',
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'draft',
                    created_at TEXT NOT NULL
                )
            """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS todo_items (
                    id TEXT PRIMARY KEY,
                    list_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    assigned_agent TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    priority TEXT DEFAULT 'medium',
                    item_order INTEGER DEFAULT 0,
                    result TEXT,
                    depends_on TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (list_id) REFERENCES todo_lists(id) ON DELETE CASCADE
                )
            """
            )
            await db.commit()

        # Migration: Add ticker and company_name if they don't exist
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "ALTER TABLE todo_lists ADD COLUMN ticker TEXT DEFAULT ''"
                )
                await db.execute(
                    "ALTER TABLE todo_lists ADD COLUMN company_name TEXT DEFAULT ''"
                )
                await db.commit()
            except Exception:
                # Columns likely already exist
                pass

        # Load existing data into cache
        await self._load_cache()
        self._initialized = True
        self.logger.info("task_manager_initialized", db_path=self.db_path)

    async def _load_cache(self):
        """Load all lists and items from SQLite into the in-memory cache."""
        import aiosqlite

        self._lists.clear()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM todo_lists") as cursor:
                async for row in cursor:
                    row_dict = dict(row)
                    tl = TodoList(
                        id=row_dict["id"],
                        deal_id=row_dict["deal_id"],
                        ticker=row_dict.get("ticker", ""),
                        company_name=row_dict.get("company_name", ""),
                        title=row_dict["title"],
                        description=row_dict["description"],
                        status=row_dict["status"],
                        created_at=row_dict["created_at"],
                    )
                    self._lists[tl.id] = tl

            async with db.execute(
                "SELECT * FROM todo_items ORDER BY item_order"
            ) as cursor:
                async for row in cursor:
                    item = TodoItem(
                        id=row["id"],
                        list_id=row["list_id"],
                        title=row["title"],
                        description=row["description"],
                        assigned_agent=row["assigned_agent"],
                        status=row["status"],
                        priority=row["priority"],
                        order=row["item_order"],
                        result=json.loads(row["result"]) if row["result"] else None,
                        depends_on=(
                            json.loads(row["depends_on"]) if row["depends_on"] else []
                        ),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    if item.list_id in self._lists:
                        self._lists[item.list_id].items.append(item)

    async def _persist_list(self, todo: TodoList):
        """Write a TodoList and all its items to SQLite."""
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO todo_lists (id, deal_id, ticker, company_name, title, description, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    todo.id,
                    todo.deal_id,
                    todo.ticker,
                    todo.company_name,
                    todo.title,
                    todo.description,
                    todo.status,
                    todo.created_at,
                ),
            )
            for item in todo.items:
                await db.execute(
                    "INSERT OR REPLACE INTO todo_items (id, list_id, title, description, assigned_agent, status, priority, item_order, result, depends_on, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.id,
                        item.list_id,
                        item.title,
                        item.description,
                        item.assigned_agent,
                        item.status,
                        item.priority,
                        item.order,
                        json.dumps(item.result) if item.result else None,
                        json.dumps(item.depends_on),
                        item.created_at,
                        item.updated_at,
                    ),
                )
            await db.commit()

    async def _persist_item(self, item: TodoItem):
        """Write a single TodoItem to SQLite."""
        import aiosqlite

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO todo_items (id, list_id, title, description, assigned_agent, status, priority, item_order, result, depends_on, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.id,
                    item.list_id,
                    item.title,
                    item.description,
                    item.assigned_agent,
                    item.status,
                    item.priority,
                    item.order,
                    json.dumps(item.result) if item.result else None,
                    json.dumps(item.depends_on),
                    item.created_at,
                    item.updated_at,
                ),
            )
            await db.commit()

    # ── CRUD ──────────────────────────────────────────────
    async def create_todo_list(
        self,
        deal_id: str,
        title: str,
        items: List[Dict[str, Any]],
        description: str = "",
        ticker: str = "",
        company_name: str = "",
    ) -> TodoList:
        """Create a new todo list with tasks and persist to SQLite."""
        await self.initialize()
        todo = TodoList(
            deal_id=deal_id,
            title=title,
            description=description,
            ticker=ticker,
            company_name=company_name,
        )
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
        await self._persist_list(todo)
        self.logger.info(
            "todo_list_created", list_id=todo.id, deal_id=deal_id, tasks=len(todo.items)
        )
        return todo

    async def get_todo_list(self, list_id: str) -> Optional[TodoList]:
        await self.initialize()
        return self._lists.get(list_id)

    async def get_lists_for_deal(self, deal_id: str) -> List[TodoList]:
        await self.initialize()
        return [tl for tl in self._lists.values() if tl.deal_id == deal_id]

    async def update_task(
        self, list_id: str, task_id: str, updates: Dict[str, Any]
    ) -> Optional[TodoItem]:
        """Update a specific task's fields and persist."""
        await self.initialize()
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
                await self._persist_item(item)
                return item
        return None

    async def delete_task(self, list_id: str, task_id: str) -> bool:
        """Remove a task from a list and from SQLite."""
        await self.initialize()
        import aiosqlite

        todo = self._lists.get(list_id)
        if not todo:
            return False
        original_len = len(todo.items)
        todo.items = [i for i in todo.items if i.id != task_id]
        if len(todo.items) < original_len:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM todo_items WHERE id = ?", (task_id,))
                await db.commit()
            return True
        return False

    async def add_task(
        self, list_id: str, item_data: Dict[str, Any]
    ) -> Optional[TodoItem]:
        """Add a new task to an existing list and persist."""
        await self.initialize()
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
        await self._persist_item(item)
        return item

    async def approve_list(self, list_id: str) -> Optional[TodoList]:
        """Mark a todo list as approved and persist."""
        await self.initialize()
        import aiosqlite

        todo = self._lists.get(list_id)
        if todo:
            todo.status = "approved"
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE todo_lists SET status = ? WHERE id = ?",
                    ("approved", list_id),
                )
                await db.commit()
        return todo

    async def reorder_tasks(self, list_id: str, task_ids: List[str]) -> bool:
        """Reorder tasks and persist new order."""
        await self.initialize()
        todo = self._lists.get(list_id)
        if not todo:
            return False
        id_to_item = {i.id: i for i in todo.items}
        new_items = []
        for idx, tid in enumerate(task_ids):
            if tid in id_to_item:
                id_to_item[tid].order = idx
                new_items.append(id_to_item[tid])
        for item in todo.items:
            if item.id not in task_ids:
                item.order = len(new_items)
                new_items.append(item)
        todo.items = new_items
        # Persist new order
        await self._persist_list(todo)
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
    async def get_next_tasks(self, list_id: str) -> List[TodoItem]:
        """Get tasks that are ready to execute (pending + dependencies met)."""
        await self.initialize()
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

    async def mark_task_result(
        self, list_id: str, task_id: str, result: Dict[str, Any]
    ) -> None:
        """Store the result of an executed task and persist."""
        await self.update_task(list_id, task_id, {"status": "done", "result": result})
        import aiosqlite

        todo = self._lists.get(list_id)
        if todo and all(i.status == "done" for i in todo.items):
            todo.status = "completed"
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE todo_lists SET status = ? WHERE id = ?",
                    ("completed", list_id),
                )
                await db.commit()


# ── Singleton ─────────────────────────────────────────────
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
