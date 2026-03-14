"""ProvenanceCollector — Audit trail for every tool call during agent execution.

Captures tool name, parameters, raw response, timestamp, and data freshness.
During workflow: records in Redis (real-time access).
On completion:  flush to PostgreSQL (long-term audit).

Redis key pattern: provenance:{deal_id}:{record_id}  (24h TTL)
"""

import json
import uuid
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = structlog.get_logger()

# TTL for Redis provenance keys (24h — auto-cleanup for abandoned workflows)
PROVENANCE_TTL_SECONDS = 86400


class ProvenanceCollector:
    """Captures and stores tool execution provenance."""

    _instance: Optional["ProvenanceCollector"] = None

    def __init__(self):
        self._memory_buffer: Dict[str, List[Dict[str, Any]]] = (
            {}
        )  # fallback if Redis unavailable

    @classmethod
    def get_instance(cls) -> "ProvenanceCollector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def record_tool_call(
        self,
        deal_id: str,
        agent_name: str,
        tool_name: str,
        params: Dict[str, Any],
        result: Any,
        execution_round: int = 1,
        data_freshness: str = "",
    ) -> str:
        """Record a tool execution with full context.

        Returns:
            provenance_id (str) for linking to agent output claims.
        """
        record_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        record = {
            "id": record_id,
            "deal_id": deal_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "tool_params": params,
            "raw_response": self._safe_serialize(result),
            "timestamp": now,
            "data_freshness": data_freshness or self._infer_freshness(result),
            "execution_round": execution_round,
            "claim_refs": [],
        }

        # Try Redis first
        try:
            from app.core.redis_store import RedisStore

            redis = RedisStore.get_instance()
            key = f"provenance:{deal_id}:{record_id}"
            await redis.client.set(key, json.dumps(record), ex=PROVENANCE_TTL_SECONDS)
            logger.info(
                "provenance_recorded",
                deal_id=deal_id,
                agent=agent_name,
                tool=tool_name,
                record_id=record_id,
            )
        except Exception as e:
            # Fallback: buffer in-memory (flushed directly to PG on completion)
            logger.warning("redis_unavailable_for_provenance", error=str(e))
            if deal_id not in self._memory_buffer:
                self._memory_buffer[deal_id] = []
            self._memory_buffer[deal_id].append(record)

        return record_id

    async def get_records(
        self,
        deal_id: str,
        agent_name: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get provenance records for a deal, optionally filtered."""
        records = []

        # Try Redis first (real-time during workflow)
        try:
            from app.core.redis_store import RedisStore

            redis = RedisStore.get_instance()
            keys = await redis.client.keys(f"provenance:{deal_id}:*")
            for key in keys:
                data = await redis.client.get(key)
                if data:
                    records.append(json.loads(data))
        except Exception:
            pass

        # Also check memory buffer
        records.extend(self._memory_buffer.get(deal_id, []))

        # If no Redis records, try PostgreSQL (post-completion)
        if not records:
            records = await self._query_postgres(deal_id)

        # Apply filters
        if agent_name:
            records = [r for r in records if r.get("agent_name") == agent_name]
        if tool_name:
            records = [r for r in records if r.get("tool_name") == tool_name]

        return sorted(records, key=lambda r: r.get("timestamp", ""))

    async def flush_to_postgres(self, deal_id: str) -> int:
        """Flush all Redis provenance records to PostgreSQL for permanent audit.

        Returns:
            count of records flushed.
        """
        records = []

        # Collect from Redis
        try:
            from app.core.redis_store import RedisStore

            redis = RedisStore.get_instance()
            keys = await redis.client.keys(f"provenance:{deal_id}:*")
            for key in keys:
                data = await redis.client.get(key)
                if data:
                    records.append(json.loads(data))
            # Delete Redis keys after collecting
            if keys:
                await redis.client.delete(*keys)
        except Exception as e:
            logger.warning("redis_flush_error", error=str(e))

        # Also collect from memory buffer
        records.extend(self._memory_buffer.pop(deal_id, []))

        if not records:
            return 0

        # Bulk insert to PostgreSQL
        try:
            from app.db.session import get_db
            from app.db.models import ProvenanceRecord

            async with AsyncSessionLocal() as session:
                for record in records:
                    db_record = ProvenanceRecord(
                        id=record["id"],
                        deal_id=record["deal_id"],
                        agent_name=record["agent_name"],
                        tool_name=record["tool_name"],
                        tool_params=record.get("tool_params"),
                        raw_response=record.get("raw_response"),
                        timestamp=datetime.fromisoformat(record["timestamp"]),
                        data_freshness=record.get("data_freshness", ""),
                        execution_round=record.get("execution_round", 1),
                        claim_refs=record.get("claim_refs"),
                    )
                    session.add(db_record)
                await session.commit()

            logger.info(
                "provenance_flushed_to_postgres",
                deal_id=deal_id,
                count=len(records),
            )
        except Exception as e:
            logger.error("provenance_postgres_flush_failed", error=str(e))

        return len(records)

    async def export_chain(self, deal_id: str) -> Dict[str, Any]:
        """Export full provenance chain for compliance."""
        records = await self.get_records(deal_id)
        return {
            "deal_id": deal_id,
            "export_timestamp": datetime.utcnow().isoformat(),
            "record_count": len(records),
            "records": records,
        }

    # ─── Internals ───

    def _safe_serialize(self, obj: Any) -> Any:
        """Safely serialize tool results for JSON storage."""
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, (list, tuple)):
            return obj
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return str(obj)

    def _infer_freshness(self, result: Any) -> str:
        """Attempt to infer data freshness from tool result."""
        if isinstance(result, dict):
            for key in ("period", "date", "fiscal_year", "report_date", "as_of"):
                if key in result:
                    return str(result[key])
        return datetime.utcnow().strftime("%Y-%m-%d")

    async def _query_postgres(self, deal_id: str) -> List[Dict[str, Any]]:
        """Query persisted provenance records from PostgreSQL."""
        try:
            from app.db.session import AsyncSessionLocal
            from app.db.models import ProvenanceRecord
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(ProvenanceRecord).where(
                    ProvenanceRecord.deal_id == deal_id
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        "id": r.id,
                        "deal_id": r.deal_id,
                        "agent_name": r.agent_name,
                        "tool_name": r.tool_name,
                        "tool_params": r.tool_params,
                        "raw_response": r.raw_response,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                        "data_freshness": r.data_freshness or "",
                        "execution_round": r.execution_round or 1,
                        "claim_refs": r.claim_refs or [],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("provenance_postgres_query_failed", error=str(e))
            return []


def get_provenance_collector() -> ProvenanceCollector:
    """Get the singleton ProvenanceCollector instance."""
    return ProvenanceCollector.get_instance()
