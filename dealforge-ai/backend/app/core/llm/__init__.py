"""LLM clients module"""

from app.core.llm.gemini_client import GeminiClient, OpenAIClient, MistralClient
from app.core.llm.local_llm_client import OllamaClient, LMStudioClient
from app.config import get_settings
import structlog

logger = structlog.get_logger()


def get_llm_client(provider=None):
    """Factory to get the configured LLM client"""
    settings = get_settings()
    provider = provider or getattr(settings, "DEFAULT_LLM_PROVIDER", "gemini").lower()

    if provider == "openai":
        return OpenAIClient()
    elif provider == "mistral":
        return MistralClient()
    elif provider == "ollama":
        return OllamaClient()
    elif provider == "lmstudio":
        return LMStudioClient()
    elif provider == "gemini":
        return GeminiClient()
    else:
        logger.warning(
            f"Unknown LLM provider '{provider}', falling back to Gemini",
            provider=provider,
        )
        return GeminiClient()


__all__ = [
    "GeminiClient",
    "OpenAIClient",
    "MistralClient",
    "OllamaClient",
    "LMStudioClient",
    "get_llm_client",
]
