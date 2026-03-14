"""
OFAS Memory Service — Cross-Agent Intelligence via MemoryEntry

Activates the existing MemoryEntry SQLAlchemy table for persistent
cross-deal intelligence. Agents can:
- Write insights after analysis (auto-tagging by agent type)
- Read insights from other agents for richer context
- Link memory entries to RAG chunk IDs for citation trails
- Query by deal, agent, tags, or recency
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger()


class MemoryService:
    """
    Service layer for the MemoryEntry table.

    Provides async read/write operations for cross-agent intelligence.
    Works with any async SQLAlchemy session factory.
    """

    def __init__(self, session_factory=None):
        """
        Args:
            session_factory: An async_sessionmaker or callable that yields
                            an AsyncSession. If None, uses the default
                            AsyncSessionLocal from app.db.session.
        """
        self._session_factory = session_factory
        self.logger = logger.bind(module="memory_service")

    def _get_session_factory(self):
        if self._session_factory:
            return self._session_factory
        from app.db.session import AsyncSessionLocal

        return AsyncSessionLocal

    async def write_memory(
        self,
        content: str,
        deal_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        chunk_id: Optional[str] = None,
        relevance_score: float = 1.0,
    ) -> Optional[str]:
        """
        Write a memory entry. Returns the entry ID.

        Args:
            content: The insight/learning to store
            deal_id: Associated deal ID
            agent_type: Agent that produced this insight
            tags: Searchable tags (e.g., ["risk", "customer_concentration"])
            chunk_id: PageIndex chunk ID for RAG citation linking
            relevance_score: Initial relevance score (0.0 - 1.0)
        """
        try:
            from app.db.models import MemoryEntry
            import uuid

            session_factory = self._get_session_factory()
            async with session_factory() as session:
                entry = MemoryEntry(
                    id=str(uuid.uuid4()),
                    content=content,
                    content_type="insight",
                    deal_id=deal_id,
                    agent_type=agent_type,
                    tags=tags or [],
                    pageindex_chunk_id=chunk_id,
                    relevance_score=relevance_score,
                    access_count=0,
                    created_at=datetime.utcnow(),
                )
                session.add(entry)
                await session.commit()

                self.logger.info(
                    "Memory written",
                    entry_id=entry.id,
                    agent=agent_type,
                    deal_id=deal_id,
                    tags=tags,
                )
                return entry.id

        except Exception as e:
            self.logger.error("Memory write failed", error=str(e))
            return None

    async def read_memory(
        self,
        deal_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        min_relevance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Read memory entries with optional filters.

        Returns list of dicts with content, agent_type, tags, chunk_id, etc.
        Also increments access_count for returned entries.
        """
        try:
            from app.db.models import MemoryEntry
            from sqlalchemy import select, desc

            session_factory = self._get_session_factory()
            async with session_factory() as session:
                query = select(MemoryEntry)

                if deal_id:
                    query = query.where(MemoryEntry.deal_id == deal_id)
                if agent_type:
                    query = query.where(MemoryEntry.agent_type == agent_type)
                if min_relevance > 0:
                    query = query.where(MemoryEntry.relevance_score >= min_relevance)

                query = query.order_by(desc(MemoryEntry.created_at)).limit(limit)

                result = await session.execute(query)
                entries = result.scalars().all()

                # Filter by tags (JSON field — do in Python)
                if tags:
                    tag_set = set(tags)
                    entries = [
                        e
                        for e in entries
                        if e.tags and tag_set.intersection(set(e.tags))
                    ]

                # Increment access counts
                for entry in entries:
                    entry.access_count = (entry.access_count or 0) + 1
                    entry.last_accessed = datetime.utcnow()
                await session.commit()

                return [
                    {
                        "id": e.id,
                        "content": e.content,
                        "agent_type": e.agent_type,
                        "deal_id": e.deal_id,
                        "tags": e.tags or [],
                        "chunk_id": e.pageindex_chunk_id,
                        "relevance_score": e.relevance_score,
                        "access_count": e.access_count,
                        "created_at": (
                            e.created_at.isoformat() if e.created_at else None
                        ),
                    }
                    for e in entries
                ]

        except Exception as e:
            self.logger.error("Memory read failed", error=str(e))
            return []

    async def link_to_rag(
        self,
        memory_id: str,
        chunk_id: str,
    ) -> bool:
        """Link an existing memory entry to a RAG chunk ID for citation trail."""
        try:
            from app.db.models import MemoryEntry
            from sqlalchemy import select

            session_factory = self._get_session_factory()
            async with session_factory() as session:
                result = await session.execute(
                    select(MemoryEntry).where(MemoryEntry.id == memory_id)
                )
                entry = result.scalar_one_or_none()
                if not entry:
                    return False

                entry.pageindex_chunk_id = chunk_id
                await session.commit()
                return True

        except Exception as e:
            self.logger.error("Link to RAG failed", error=str(e))
            return False

    async def get_cross_deal_insights(
        self,
        industry: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get insights across multiple deals — useful for pattern recognition.
        Returns the most accessed, highest-relevance entries.
        """
        try:
            from app.db.models import MemoryEntry
            from sqlalchemy import select, desc

            session_factory = self._get_session_factory()
            async with session_factory() as session:
                query = (
                    select(MemoryEntry)
                    .order_by(
                        desc(MemoryEntry.relevance_score),
                        desc(MemoryEntry.access_count),
                    )
                    .limit(limit)
                )

                if agent_type:
                    query = query.where(MemoryEntry.agent_type == agent_type)

                result = await session.execute(query)
                entries = result.scalars().all()

                # Filter by industry tag if provided
                if industry:
                    entries = [
                        e
                        for e in entries
                        if e.tags and industry.lower() in [t.lower() for t in e.tags]
                    ]

                return [
                    {
                        "content": e.content,
                        "deal_id": e.deal_id,
                        "agent_type": e.agent_type,
                        "relevance_score": e.relevance_score,
                        "access_count": e.access_count,
                    }
                    for e in entries
                ]

        except Exception as e:
            self.logger.error("Cross-deal insights failed", error=str(e))
            return []


# Singleton
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    """Get the global MemoryService instance"""
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
