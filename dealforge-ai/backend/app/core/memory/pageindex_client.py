"""PageIndex Client for Document RAG — Supports both local and cloud modes"""

import httpx
import json
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.config import get_settings
import structlog

logger = structlog.get_logger()


@dataclass
class PageIndexChunk:
    """Represents a chunk from PageIndex"""

    chunk_id: str
    content: str
    page_number: int
    metadata: Dict[str, Any]
    relevance_score: float = 0.0


@dataclass
class IndexResult:
    """Result from indexing a document"""

    index_id: str
    document_id: str
    total_pages: int
    total_chunks: int
    metadata: Dict[str, Any]


class PageIndexClient:
    """
    Client for PageIndex RAG — supports both self-hosted local mode
    and VectifyAI cloud API.

    Local mode (default): Uses LocalPageIndexService to build tree indexes
    and search them locally without any cloud dependency.

    Cloud mode: Falls back to VectifyAI API when PAGEINDEX_API_KEY is set
    and PAGEINDEX_MODE is "cloud".
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.PAGEINDEX_API_KEY
        self.base_url = base_url or settings.PAGEINDEX_BASE_URL
        self.mode = mode or getattr(settings, "PAGEINDEX_MODE", "local")

        # Initialize the appropriate backend
        self._local_service = None

        if self.mode == "local":
            self._init_local()
        elif not self.api_key:
            logger.warning(
                "PageIndex API key not configured, falling back to local mode"
            )
            self.mode = "local"
            self._init_local()

    def _init_local(self):
        """Initialize the local PageIndex service"""
        try:
            from app.core.memory.local_pageindex import get_local_pageindex
            from app.core.llm.model_router import get_model_router

            settings = get_settings()
            router = get_model_router()

            # Determine explicit model routing
            provider = router.get_provider_for_agent("pageindex")
            model_env_key = f"{provider.upper()}_MODEL"
            provider_model = getattr(settings, model_env_key, None)

            # Default fallback for reasoning models
            if not provider_model:
                if provider == "openai":
                    provider_model = "gpt-4o"
                elif provider == "ollama":
                    provider_model = "llama3"
                elif provider == "mistral":
                    provider_model = "mistral-large-latest"
                elif provider == "lmstudio":
                    provider_model = "local-model"
                else:
                    provider_model = "gemini-2.5-flash"

            use_gemini = provider == "gemini"

            self._local_service = get_local_pageindex(
                storage_dir=settings.PAGEINDEX_STORAGE_DIR,
                openai_api_key=settings.OPENAI_API_KEY,
                gemini_api_key=settings.GEMINI_API_KEY,
                model=provider_model,
                use_gemini=use_gemini,
            )
            logger.info(
                "PageIndex running in LOCAL mode (self-hosted)",
                provider=provider,
                model=provider_model,
            )
        except Exception as e:
            logger.error("Failed to init local PageIndex", error=str(e))

    # ===== Cloud API (original) =====

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to PageIndex cloud API"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if files:
                    response = await client.request(
                        method, url, headers=headers, data=data, files=files
                    )
                else:
                    headers["Content-Type"] = "application/json"
                    response = await client.request(
                        method, url, headers=headers, json=data
                    )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "PageIndex API error",
                    status_code=e.response.status_code,
                    response=e.response.text,
                    endpoint=endpoint,
                )
                raise
            except Exception as e:
                logger.error(
                    "PageIndex request failed", error=str(e), endpoint=endpoint
                )
                raise

    # ===== Unified API (local or cloud) =====

    async def ingest_document(
        self, file_path: str, metadata: Optional[Dict[str, Any]] = None
    ) -> IndexResult:
        """
        Ingest a document into PageIndex.

        In local mode: builds a tree index on disk.
        In cloud mode: uploads to VectifyAI API.
        """
        logger.info("Ingesting document", file_path=file_path, mode=self.mode)

        if self.mode == "local" and self._local_service:
            doc = await self._local_service.index_document(file_path, metadata)
            return IndexResult(
                index_id=doc.index_id,
                document_id=doc.doc_id,
                total_pages=doc.total_pages,
                total_chunks=doc.total_nodes,
                metadata=doc.metadata,
            )

        # Cloud mode
        with open(file_path, "rb") as f:
            file_content = f.read()

        filename = file_path.split("/")[-1]
        files = {"file": (filename, file_content, "application/octet-stream")}
        data = {"metadata": json.dumps(metadata or {})}

        result = await self._request("POST", "documents", data=data, files=files)

        return IndexResult(
            index_id=result["index_id"],
            document_id=result["document_id"],
            total_pages=result.get("total_pages", 0),
            total_chunks=result.get("total_chunks", 0),
            metadata=result.get("metadata", {}),
        )

    async def ingest_text(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> IndexResult:
        """Ingest raw text content into PageIndex"""
        logger.info("Ingesting text", content_length=len(content), mode=self.mode)

        if self.mode == "local" and self._local_service:
            title = (metadata or {}).get("title", "Untitled")
            doc = await self._local_service.index_text(content, title, metadata)
            return IndexResult(
                index_id=doc.index_id,
                document_id=doc.doc_id,
                total_pages=doc.total_pages,
                total_chunks=doc.total_nodes,
                metadata=doc.metadata,
            )

        # Cloud mode
        data = {"content": content, "metadata": metadata or {}}
        result = await self._request("POST", "documents/text", data=data)

        return IndexResult(
            index_id=result["index_id"],
            document_id=result["document_id"],
            total_pages=result.get("total_pages", 1),
            total_chunks=result.get("total_chunks", 0),
            metadata=result.get("metadata", {}),
        )

    async def query(
        self,
        query: str,
        index_id: Optional[str] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[PageIndexChunk]:
        """
        Query the index for relevant chunks.

        In local mode: searches tree structures on disk.
        In cloud mode: calls VectifyAI API.
        """
        logger.info("Querying PageIndex", query=query, top_k=top_k, mode=self.mode)

        if self.mode == "local" and self._local_service:
            deal_id = (filters or {}).get("deal_id")
            results = await self._local_service.query(
                query, index_id=index_id, deal_id=deal_id, top_k=top_k
            )

            chunks = [
                PageIndexChunk(
                    chunk_id=r.chunk_id,
                    content=r.content,
                    page_number=r.page_number,
                    metadata=r.metadata,
                    relevance_score=r.relevance_score,
                )
                for r in results
            ]

            logger.info("Local query returned chunks", count=len(chunks))
            return chunks

        # Cloud mode
        data = {"query": query, "top_k": top_k, "filters": filters or {}}

        if index_id:
            data["index_id"] = index_id

        result = await self._request("POST", "query", data=data)

        chunks = []
        for chunk_data in result.get("chunks", []):
            chunks.append(
                PageIndexChunk(
                    chunk_id=chunk_data["chunk_id"],
                    content=chunk_data["content"],
                    page_number=chunk_data.get("page_number", 0),
                    metadata=chunk_data.get("metadata", {}),
                    relevance_score=chunk_data.get("relevance_score", 0.0),
                )
            )

        logger.info("PageIndex query returned chunks", count=len(chunks))
        return chunks

    async def delete_index(self, index_id: str) -> bool:
        """Delete an index"""
        if self.mode == "local" and self._local_service:
            # Find doc by index_id
            for doc in self._local_service.list_documents():
                if doc.index_id == index_id:
                    return self._local_service.delete_document(doc.doc_id)
            return False

        try:
            await self._request("DELETE", f"documents/{index_id}")
            logger.info("Deleted PageIndex", index_id=index_id)
            return True
        except Exception as e:
            logger.error("Failed to delete PageIndex", index_id=index_id, error=str(e))
            return False

    async def get_index_status(self, index_id: str) -> Dict[str, Any]:
        """Get the status of an index"""
        if self.mode == "local" and self._local_service:
            return self._local_service.get_stats()

        return await self._request("GET", f"documents/{index_id}/status")

    def get_stats(self) -> Dict[str, Any]:
        """Get overall stats (local mode only)"""
        if self._local_service:
            return self._local_service.get_stats()
        return {"mode": "cloud", "status": "connected"}


# Singleton instance
_pageindex_client: Optional[PageIndexClient] = None


def get_pageindex_client() -> PageIndexClient:
    """Get or create PageIndex client singleton"""
    global _pageindex_client
    if _pageindex_client is None:
        _pageindex_client = PageIndexClient()
    return _pageindex_client
