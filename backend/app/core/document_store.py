"""
Document Artifact Store — Redis-backed cache for generated deal reports.

Stores PPTX, Excel, and PDF artifacts with metadata so reports are generated
once and served instantly on subsequent downloads.
"""

import json
import os
import base64
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime
import redis.asyncio as redis

logger = structlog.get_logger()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# 24-hour TTL for cached documents
DOCUMENT_TTL_SECONDS = 86400


class DocumentStore:
    """Redis-backed document artifact cache for deal reports."""

    _instance: Optional["DocumentStore"] = None

    def __init__(self):
        # Use a separate client without decode_responses for binary data
        self.client = redis.from_url(REDIS_URL, decode_responses=False)
        # Text client for metadata
        self.meta_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("document_store_initialized", url=REDIS_URL)

    @classmethod
    def get_instance(cls) -> "DocumentStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ═══════════════════════════════════════════════════════════
    #  Save / Retrieve Document Artifacts
    # ═══════════════════════════════════════════════════════════

    async def save_document(
        self,
        deal_id: str,
        fmt: str,
        content_bytes: bytes,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Cache a generated document artifact.
        
        Args:
            deal_id: The deal identifier
            fmt: Format key (pdf, pptx, xlsx)
            content_bytes: Raw file bytes
            metadata: Optional metadata (company name, agent count, etc.)
        """
        doc_key = f"doc:{deal_id}:{fmt}"
        meta_key = f"docmeta:{deal_id}:{fmt}"

        meta = {
            "deal_id": deal_id,
            "format": fmt,
            "size_bytes": len(content_bytes),
            "size_human": self._human_size(len(content_bytes)),
            "generated_at": datetime.utcnow().isoformat(),
            "status": "ready",
            **(metadata or {}),
        }

        # Store binary content
        await self.client.set(doc_key, content_bytes, ex=DOCUMENT_TTL_SECONDS)
        # Store metadata as JSON
        await self.meta_client.set(
            meta_key, json.dumps(meta), ex=DOCUMENT_TTL_SECONDS
        )

        # Add to deal's document index
        await self.meta_client.sadd(f"docindex:{deal_id}", fmt)
        await self.meta_client.expire(f"docindex:{deal_id}", DOCUMENT_TTL_SECONDS)

        logger.info(
            "document_cached",
            deal_id=deal_id,
            format=fmt,
            size=meta["size_human"],
        )

    async def get_document(self, deal_id: str, fmt: str) -> Optional[bytes]:
        """Retrieve cached document bytes. Returns None on cache miss."""
        doc_key = f"doc:{deal_id}:{fmt}"
        return await self.client.get(doc_key)

    async def get_document_meta(
        self, deal_id: str, fmt: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a cached document."""
        meta_key = f"docmeta:{deal_id}:{fmt}"
        data = await self.meta_client.get(meta_key)
        if data:
            return json.loads(data)
        return None

    # ═══════════════════════════════════════════════════════════
    #  Manifest & Listing
    # ═══════════════════════════════════════════════════════════

    async def list_documents(self, deal_id: str) -> List[Dict[str, Any]]:
        """
        Return a manifest of all available documents for a deal.
        Each entry includes format, size, timestamp, and download status.
        """
        formats = await self.meta_client.smembers(f"docindex:{deal_id}")
        if not formats:
            return []

        documents = []
        for fmt in sorted(formats):
            meta = await self.get_document_meta(deal_id, fmt)
            if meta:
                documents.append(meta)

        return documents

    async def has_documents(self, deal_id: str) -> bool:
        """Check if any cached documents exist for a deal."""
        return await self.meta_client.scard(f"docindex:{deal_id}") > 0

    # ═══════════════════════════════════════════════════════════
    #  Invalidation
    # ═══════════════════════════════════════════════════════════

    async def invalidate(self, deal_id: str):
        """Clear all cached documents for a deal (e.g., after re-analysis)."""
        formats = await self.meta_client.smembers(f"docindex:{deal_id}")
        if formats:
            keys_to_delete = []
            for fmt in formats:
                keys_to_delete.append(f"doc:{deal_id}:{fmt}")
                keys_to_delete.append(f"docmeta:{deal_id}:{fmt}")

            # Delete binary keys
            binary_keys = [f"doc:{deal_id}:{fmt}".encode() for fmt in formats]
            if binary_keys:
                await self.client.delete(*binary_keys)

            # Delete meta keys
            meta_keys = [f"docmeta:{deal_id}:{fmt}" for fmt in formats]
            if meta_keys:
                await self.meta_client.delete(*meta_keys)

        await self.meta_client.delete(f"docindex:{deal_id}")
        logger.info("documents_invalidated", deal_id=deal_id)

    # ═══════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _human_size(nbytes: int) -> str:
        """Convert bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if nbytes < 1024:
                return f"{nbytes:.1f} {unit}"
            nbytes /= 1024
        return f"{nbytes:.1f} TB"

    @staticmethod
    def get_content_type(fmt: str) -> str:
        """Return MIME type for a format key."""
        return {
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
        }.get(fmt, "application/octet-stream")

    @staticmethod
    def get_extension(fmt: str) -> str:
        """Normalize format key to file extension."""
        return {"excel": "xlsx"}.get(fmt, fmt)

    async def close(self):
        await self.client.aclose()
        await self.meta_client.aclose()
