"""DealForge AI Configuration"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # App
    APP_NAME: str = "DealForge AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/dealforge"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # OpenAI / Codex
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    CODEX_MODEL: str = "gpt-5.1-codex-max"

    # Mistral
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_MODEL: str = "mistral-large-latest"

    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"

    # Local LLMs
    DEFAULT_LLM_PROVIDER: str = "gemini"  # gemini, openai, mistral, ollama, lmstudio
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LMSTUDIO_MODEL: str = "local-model"

    # PageIndex
    PAGEINDEX_API_KEY: Optional[str] = None
    PAGEINDEX_BASE_URL: str = "https://api.vectify.ai/v1"
    PAGEINDEX_MODE: str = "local"  # "local" (self-hosted) or "cloud" (VectifyAI API)
    PAGEINDEX_STORAGE_DIR: Optional[str] = None  # Local storage path for indexes

    # Agent Settings
    MAX_AGENT_ITERATIONS: int = 10
    AGENT_TIMEOUT_SECONDS: int = 300
    AGENT_MODEL_MAP: Optional[str] = None

    # Deal Scoring
    DEAL_SCORING_THRESHOLD: float = 0.65

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
