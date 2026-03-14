import aiosqlite
import json
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime
import os

from app.config import get_settings


class AgentQualityStore:
    """
    Tracks and stores analytical success patterns and agent performance scores
    to enable Reinforcement Learning (RL) based self-improvement.
    """

    def __init__(self, db_path: str = None):
        if not db_path:
            settings = get_settings()
            self.db_path = os.path.join(settings.DATA_DIR, "agent_quality.db")
        else:
            self.db_path = db_path

        self.logger = structlog.get_logger()

    async def initialize(self):
        """Initialize the SQLite database schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            # Table for recording historical task actions and their ultimate score
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    deal_context_hash TEXT NOT NULL,
                    action_payload TEXT NOT NULL,
                    score REAL,
                    feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Table for distilled "best practices" based on high-scoring actions
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS best_practices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    practice_description TEXT NOT NULL,
                    avg_score REAL NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def log_action(
        self,
        agent_name: str,
        task_type: str,
        deal_context: Dict[str, Any],
        action_payload: Dict[str, Any],
    ) -> int:
        """
        Log an agent's action BEFORE we know the final score.
        Returns the action ID to later attach a reward.
        """
        # Hash deal context slightly to categorize deal types
        industry = deal_context.get("industry", "general")
        deal_type = deal_context.get("type", "general")
        context_hash = f"{industry}_{deal_type}"

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO agent_actions (agent_name, task_type, deal_context_hash, action_payload)
                VALUES (?, ?, ?, ?)
                """,
                (agent_name, task_type, context_hash, json.dumps(action_payload)),
            )
            await db.commit()
            return cursor.lastrowid

    async def reward_action(self, action_id: int, score: float, feedback: str = ""):
        """
        Attach a reward signal to a previously logged action.
        This closes the RL loop.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE agent_actions 
                SET score = ?, feedback = ?
                WHERE id = ?
                """,
                (score, feedback, action_id),
            )
            await db.commit()

    async def update_best_practices(self, agent_name: str, task_type: str):
        """
        Analyze high-scoring actions to extract recurring patterns and update best practices.
        In a real RL system, an LLM would summarize the action payloads.
        Here we simply aggregate top actions.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get top 5 highest scoring actions for this agent+task
            async with db.execute(
                """
                SELECT action_payload, score, feedback FROM agent_actions
                WHERE agent_name = ? AND task_type = ? AND score > 0.7
                ORDER BY score DESC LIMIT 5
                """,
                (agent_name, task_type),
            ) as cursor:
                top_actions = await cursor.fetchall()

            if not top_actions:
                return

            # Naive extraction for proof-of-concept
            # We construct a summary of what worked
            avg_score = sum(row[1] for row in top_actions) / len(top_actions)

            # Formulate the "practice"
            feedbacks = [row[2] for row in top_actions if row[2]]
            if feedbacks:
                practice_desc = (
                    f"Historically successful approach: {' | '.join(feedbacks)}"
                )
            else:
                practice_desc = "Historically successful approach: Ensure deep data coverage using available tools."

            # Upsert into best_practices
            await db.execute(
                """
                INSERT INTO best_practices (agent_name, task_type, practice_description, avg_score)
                VALUES (?, ?, ?, ?)
                """,
                (agent_name, task_type, practice_desc, avg_score),
            )
            await db.commit()

    async def get_historical_best_practices(
        self, agent_name: str, task_type: str
    ) -> List[str]:
        """
        Retrieve best practices to inject into the LLM system prompt prior to execution.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT practice_description FROM best_practices
                WHERE agent_name = ? AND task_type = ?
                ORDER BY avg_score DESC LIMIT 3
                """,
                (agent_name, task_type),
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    # ===== Replication Tracking =====
    async def log_replication_run(
        self, agent_name: str, task_type: str, outputs: List[str]
    ) -> int:
        """
        Store a batch of outputs from repeated agent executions and compute
        a simple similarity metric. Returns the replication record ID.
        """
        # compute pairwise similarities
        from difflib import SequenceMatcher

        sims = []
        n = len(outputs)
        for i in range(n):
            for j in range(i + 1, n):
                m = SequenceMatcher(None, outputs[i], outputs[j])
                sims.append(m.ratio())
        avg_sim = sum(sims) / len(sims) if sims else 1.0
        min_sim = min(sims) if sims else 1.0

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO replication_runs (agent_name, task_type, outputs, avg_similarity, min_similarity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    agent_name,
                    task_type,
                    json.dumps(outputs),
                    avg_sim,
                    min_sim,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_recent_replication(
        self, agent_name: str, task_type: str, limit: int = 5
    ):
        """
        Return recent replication statistics for a given agent/task.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, outputs, avg_similarity, min_similarity, created_at
                FROM replication_runs
                WHERE agent_name = ? AND task_type = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (agent_name, task_type, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    results.append(
                        {
                            "id": row[0],
                            "outputs": json.loads(row[1]),
                            "avg_similarity": row[2],
                            "min_similarity": row[3],
                            "created_at": row[4],
                        }
                    )
                return results
