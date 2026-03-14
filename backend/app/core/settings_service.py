"""
Settings Persistence Service — Save/Load application settings to JSON file.

Settings are stored in a local JSON file and loaded at startup.
When saved, they update the in-memory config and re-initialize dependent services.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import structlog

logger = structlog.get_logger()

# Default settings file path
SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "settings.json"
)


class SettingsService:
    """Persist and apply runtime settings."""

    _instance: Optional["SettingsService"] = None

    def __init__(self, file_path: str = SETTINGS_FILE):
        self.file_path = os.path.abspath(file_path)
        self._settings: Dict[str, Any] = {}
        self._load()

    @classmethod
    def get_instance(cls) -> "SettingsService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        """Load settings from JSON file."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r") as f:
                    self._settings = json.load(f)
                logger.info(
                    "settings_loaded", path=self.file_path, keys=len(self._settings)
                )
            else:
                self._settings = self._defaults()
                self._save()
                logger.info("settings_created_default", path=self.file_path)
        except Exception as e:
            logger.error("settings_load_error", error=str(e))
            self._settings = self._defaults()

    def _save(self):
        """Write current settings to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump(self._settings, f, indent=2, default=str)
            logger.info("settings_saved", path=self.file_path)
        except Exception as e:
            logger.error("settings_save_error", error=str(e))

    @staticmethod
    def _defaults() -> Dict[str, Any]:
        return {
            # API Keys
            "gemini_api_key": "",
            "openai_api_key": "",
            "mistral_api_key": "",
            # Model selections
            "gemini_model": "",
            # NVIDIA
            "nvidia_api_key": "",
            "nvidia_base_url": "https://integrate.api.nvidia.com/v1",
            "nvidia_model": "z-ai/glm5",
            # Vertex AI
            "vertex_api_key": "",
            "vertex_project_id": "",
            "vertex_location": "us-central1",
            "vertex_model": "gemini-1.5-flash-002",
            "openai_model": "",
            "mistral_model": "",
            # Local LLMs
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3",
            "lmstudio_base_url": "http://localhost:1234/v1",
            "lmstudio_model": "local-model",
            # Default provider
            "default_llm_provider": "gemini",
            # Agent routing
            "agent_routing": {
                "financial_analyst": "gemini",
                "valuation_agent": "gemini",
                "dcf_lbo_architect": "gemini",
                "legal_advisor": "gemini",
                "risk_assessor": "gemini",
                "debate_moderator": "gemini",
                "market_researcher": "ollama",
                "market_risk_agent": "ollama",
                "compliance_agent": "ollama",
                "scoring_agent": "ollama",
                "pageindex": "gemini",
                "advanced_financial_modeler": "gemini",
                "complex_reasoning": "gemini",
                "data_curator": "gemini",
                "report_architect": "gemini",
                "due_diligence_agent": "gemini",
                "investment_memo_agent": "gemini",
                "red_team": "gemini",
                "business_analyst": "gemini",
                "esg_agent": "ollama",
                "integration_planner_agent": "gemini",
                "project_manager": "gemini"
            },
            # RAG
            "pageindex_mode": "local",
            # Gateway cost controls
            "gateway": {
                "gemini_max_rpm": 12,
                "gemini_max_tpm": 80000,
                "openai_max_rpm": 50,
                "openai_max_tpm": 150000,
                "mistral_max_rpm": 5,
                "mistral_max_tpm": 400000,
                "cache_enabled": True,
                "hybrid_compression": True,
                "daily_budget_usd": 0,
            },
            # Web Search Fallback
            "search_priority": ["serper", "searxng", "ddg"],
            "serper_api_key": "",
            "searxng_instance_url": "",
            "searxng_api_key": "",
            "fmp_api_key": "",
            "financial_datasets_api_key": "",
            "alpha_vantage_api_key": "",
            "finnhub_api_key": "",
        }

    def get_all(self) -> Dict[str, Any]:
        """Return all settings."""
        return dict(self._settings)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update settings and persist."""
        self._settings.update(updates)
        self._save()
        self._apply_to_system()
        return self._settings

    def _apply_to_system(self):
        """
        Apply settings changes to running system components.
        Re-initializes LLM gateway limits and model router.
        """
        try:
            # Update gateway rate limits
            gateway_cfg = self._settings.get("gateway", {})
            if gateway_cfg:
                from app.core.llm.llm_gateway import get_llm_gateway, VendorLimits

                gw = get_llm_gateway()
                for vendor in ["gemini", "openai", "mistral", "nvidia"]:
                    rpm = gateway_cfg.get(f"{vendor}_max_rpm")
                    tpm = gateway_cfg.get(f"{vendor}_max_tpm")
                    if rpm or tpm:
                        gw.update_vendor_limits(
                            vendor,
                            VendorLimits(
                                max_rpm=rpm or 50,
                                max_tpm=tpm or 100_000,
                            ),
                        )

            # Update model router if agent_routing changed
            routing = self._settings.get("agent_routing")
            if routing:
                from app.core.llm.model_router import get_model_router

                router = get_model_router()
                router.agent_routing.update(routing)
                logger.info("model_router_updated", agents=len(routing))

            # Update environment-style settings for LLM clients
            api_key_map = {
                "gemini_api_key": "GEMINI_API_KEY",
                "vertex_api_key": "VERTEX_API_KEY",
                "vertex_project_id": "VERTEX_PROJECT_ID",
                "vertex_location": "VERTEX_LOCATION",
                "vertex_model": "VERTEX_MODEL",
                "openai_api_key": "OPENAI_API_KEY",
                "mistral_api_key": "MISTRAL_API_KEY",
                "gemini_model": "GEMINI_MODEL",
                "openai_model": "OPENAI_MODEL",
                "mistral_model": "MISTRAL_MODEL",
                "ollama_base_url": "OLLAMA_BASE_URL",
                "ollama_model": "OLLAMA_MODEL",
                "ollama_model": "OLLAMA_MODEL",
                "lmstudio_base_url": "LMSTUDIO_BASE_URL",
                "lmstudio_model": "LMSTUDIO_MODEL",
                "nvidia_api_key": "NVIDIA_API_KEY",
                "nvidia_base_url": "NVIDIA_BASE_URL",
                "nvidia_model": "NVIDIA_MODEL",
                "default_llm_provider": "DEFAULT_LLM_PROVIDER",
                "pageindex_mode": "PAGEINDEX_MODE",
                "fmp_api_key": "FMP_API_KEY",
                "financial_datasets_api_key": "FINANCIAL_DATASETS_API_KEY",
                "alpha_vantage_api_key": "ALPHA_VANTAGE_API_KEY",
                "finnhub_api_key": "FINNHUB_API_KEY",
            }
            for ui_key, env_key in api_key_map.items():
                val = self._settings.get(ui_key, "")
                if val and val != "***":
                    os.environ[env_key] = str(val)

            # Clear the Pydantic settings cache so future get_settings() calls pull the new env vars
            from app.config import get_settings

            get_settings.cache_clear()

            # Reset PageIndex and RAG singletons so they re-initialize with new routing/keys
            try:
                import app.core.memory.pageindex_client as pic
                import app.core.memory.local_pageindex as lpi

                pic._pageindex_client = None
                lpi._local_pageindex = None
                logger.info("rag_singletons_reset")
            except ImportError:
                pass

            # Sync search settings to MCP runtime keys
            try:
                from app.core.mcp import _runtime_keys

                _runtime_keys["search_priority"] = self._settings.get(
                    "search_priority", ["serper", "searxng", "ddg"]
                )
                _runtime_keys["serper"] = self._settings.get("serper_api_key", "")
                _runtime_keys["searxng"] = self._settings.get(
                    "searxng_instance_url", ""
                )
                # SearXNG key if needed
                if self._settings.get("searxng_api_key"):
                    _runtime_keys["searxng_key"] = self._settings.get("searxng_api_key")
                logger.info("mcp_search_settings_synced")
            except ImportError:
                pass

            logger.info("settings_applied_to_system")

        except Exception as e:
            logger.error("settings_apply_error", error=str(e))
