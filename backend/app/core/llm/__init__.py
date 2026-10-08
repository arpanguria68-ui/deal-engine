"""LLM clients module"""

from typing import Any, Callable, Dict
import threading

from app.core.llm.gemini_client import GeminiClient, OpenAIClient, MistralClient
from app.core.llm.local_llm_client import OllamaClient, LMStudioClient
from app.core.llm.nvidia_client import NvidiaClient
from app.config import get_settings
import structlog

logger = structlog.get_logger()


# provider name → zero-arg factory. Extra providers (e.g. the offline "mock"
# provider used by the harness) can be added with register_llm_client().
_CLIENT_FACTORIES: Dict[str, Callable[[], Any]] = {
    "openai": OpenAIClient,
    "mistral": MistralClient,
    "ollama": OllamaClient,
    "lmstudio": LMStudioClient,
    "gemini": GeminiClient,
    "nvidia": NvidiaClient,
    # Vertex AI uses the same underlying Gemini logic but different auth/endpoint
    "vertex": lambda: GeminiClient(provider="vertex"),
}

# Clients are pooled per provider: each one owns an HTTP connection pool, so
# building a fresh client on every call leaked sockets and re-did SDK setup.
_client_pool: Dict[str, Any] = {}
_pool_lock = threading.Lock()


def register_llm_client(provider: str, factory: Callable[[], Any]) -> None:
    """Register (or replace) a client factory for a provider name."""
    _CLIENT_FACTORIES[provider] = factory
    _client_pool.pop(provider, None)


def reset_llm_clients() -> None:
    """Drop pooled clients so the next call picks up changed keys/models."""
    with _pool_lock:
        _client_pool.clear()


def get_llm_client(provider=None):
    """Get the pooled LLM client for a provider (defaults to DEFAULT_LLM_PROVIDER)."""
    settings = get_settings()
    provider = (
        provider or getattr(settings, "DEFAULT_LLM_PROVIDER", "gemini")
    ).lower()

    if provider not in _CLIENT_FACTORIES:
        logger.warning(
            f"Unknown LLM provider '{provider}', falling back to Gemini",
            provider=provider,
        )
        provider = "gemini"

    client = _client_pool.get(provider)
    if client is None:
        with _pool_lock:
            client = _client_pool.get(provider)
            if client is None:
                client = _CLIENT_FACTORIES[provider]()
                _client_pool[provider] = client
    return client


__all__ = [
    "GeminiClient",
    "OpenAIClient",
    "MistralClient",
    "OllamaClient",
    "LMStudioClient",
    "NvidiaClient",
    "get_llm_client",
    "register_llm_client",
    "reset_llm_clients",
]
