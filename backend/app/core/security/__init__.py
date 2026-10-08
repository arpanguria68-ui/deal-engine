"""
API access guardrails.

* API key (opt-in): when DEALFORGE_API_KEY is set, every /api/ request must
  send it as `Authorization: Bearer <key>` or `X-API-Key: <key>`. Unset keeps
  today's open behaviour (a warning is logged at startup) so local dev and the
  current frontend keep working.
* LLM rate limit: endpoints that spend LLM quota take the `llm_rate_limit`
  dependency — a per-client sliding window (DEALFORGE_LLM_RPM requests per
  minute, default 30; 0 disables).
"""

import hmac
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

import structlog
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger()

# Reachable without a key: health probes and CORS preflight
PUBLIC_PATHS = {"/", "/health", "/api/v1/health", "/docs", "/openapi.json"}


def _configured_api_key() -> str:
    return os.environ.get("DEALFORGE_API_KEY", "")


def _presented_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key", "").strip()


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        key = _configured_api_key()
        path = request.url.path
        if (
            key
            and path.startswith("/api/")
            and path not in PUBLIC_PATHS
            and request.method != "OPTIONS"
            and not hmac.compare_digest(_presented_key(request), key)
        ):
            return JSONResponse({"detail": "Missing or invalid API key"}, status_code=401)
        return await call_next(request)


def warn_if_open() -> None:
    if not _configured_api_key():
        logger.warning(
            "api_unauthenticated",
            detail="DEALFORGE_API_KEY is not set: settings, gateway and agent "
            "endpoints are open to anyone who can reach this server.",
        )


class SlidingWindowLimiter:
    """Per-client request counter over a rolling window."""

    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit = limit
        self.window_s = window_s
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, client: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        hits = self._hits[client]
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def retry_after(self, client: str) -> int:
        hits = self._hits.get(client)
        if not hits:
            return 0
        return max(1, int(self.window_s - (time.monotonic() - hits[0])) + 1)


_llm_limiter = SlidingWindowLimiter(int(os.environ.get("DEALFORGE_LLM_RPM", "30")))


def _client_id(request: Request) -> str:
    key = _presented_key(request)
    if key:
        return "key:" + key[-8:]
    return "ip:" + (request.client.host if request.client else "unknown")


async def llm_rate_limit(request: Request) -> None:
    """FastAPI dependency for endpoints that spend LLM quota."""
    client = _client_id(request)
    if not _llm_limiter.allow(client):
        logger.warning("llm_rate_limited", client=client, path=request.url.path)
        raise HTTPException(
            status_code=429,
            detail="Too many LLM requests; slow down.",
            headers={"Retry-After": str(_llm_limiter.retry_after(client))},
        )
