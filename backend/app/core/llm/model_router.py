"""
Smart Model Router — Local-First with Cloud Fallback

Strategy:
1. Try local LLM (Ollama/LM Studio) first for ALL agents
2. If local fails (timeout, not running), fallback to cloud (Gemini/OpenAI)
3. Complex reasoning agents can be forced to cloud via routing table
4. Logs which provider was actually used for transparency

Mimics how McKinsey staffs: try junior analyst first, escalate to partner if needed.
"""

import os
from typing import Dict, Optional, Tuple
import structlog
import httpx
from app.core.settings_service import SettingsService

logger = structlog.get_logger()


# Default routing table: agent_name → preferred provider
DEFAULT_AGENT_ROUTING = {
    # ===== Complex reasoning → Local LLM (Performance Eval) =====
    "financial_analyst": "lmstudio",
    "valuation_agent": "lmstudio",
    "legal_advisor": "lmstudio",
    "risk_assessor": "lmstudio",
    "debate_moderator": "lmstudio",
    "due_diligence_agent": "lmstudio",
    "investment_memo_agent": "lmstudio",
    "compliance_qa_agent": "lmstudio",
    "dcf_lbo_architect": "lmstudio",
    "ofas_supervisor": "lmstudio",
    "complex_reasoning": "gemini",  # Forced to cloud for complex Chain-of-Thought
    "advanced_financial_modeler": "gemini",  # High logic load
    "data_curator": "lmstudio",
    "report_architect": "lmstudio",
    # ===== Lighter tasks → Local LLM =====
    "market_researcher": "lmstudio",
    "market_risk_agent": "lmstudio",
    "compliance_agent": "lmstudio",
    "scoring_agent": "lmstudio",
}


# Task-type routing for ad-hoc requests
TASK_TYPE_ROUTING = {
    "analysis": "gemini",
    "reasoning": "gemini",
    "valuation": "gemini",
    "legal": "gemini",
    "debate": "gemini",
    "extraction": "ollama",
    "formatting": "ollama",
    "summarization": "ollama",
    "classification": "ollama",
}

# Cloud providers that can serve as fallback
CLOUD_PROVIDERS = {"gemini", "vertex", "openai", "mistral", "nvidia"}
LOCAL_PROVIDERS = {"ollama", "lmstudio"}


class ModelRouter:
    """
    Routes agents to optimal LLM with local-first fallback.

    Priority order:
    1. If agent is assigned LOCAL → try local first, fallback to cloud
    2. If agent is assigned CLOUD → use cloud directly
    3. If local provider is offline → auto-fallback to cloud
    """

    def __init__(self):
        settings = SettingsService.get_instance()
        self.fallback_provider = settings.get("default_llm_provider", "gemini")
        # Use the user's default provider as cloud fallback instead of hardcoded gemini
        self.cloud_fallback = self.fallback_provider if self.fallback_provider in CLOUD_PROVIDERS else "gemini"

        # Local LLM health cache
        self._local_health: Dict[str, bool] = {}

        # Load routing table
        self.agent_routing = dict(DEFAULT_AGENT_ROUTING)

        dynamic_map = settings.get("agent_routing", {})
        if dynamic_map:
            self.agent_routing.update(dynamic_map)
            logger.info(
                "Custom agent model map loaded from SettingsService",
                overrides=dynamic_map,
            )

        logger.info(
            "ModelRouter initialized (local-first)",
            routing_summary={
                "cloud_agents": [
                    k for k, v in self.agent_routing.items() if v in CLOUD_PROVIDERS
                ],
                "local_agents": [
                    k for k, v in self.agent_routing.items() if v in LOCAL_PROVIDERS
                ],
                "fallback": self.fallback_provider,
            },
        )

    async def check_local_health(self, provider: str) -> bool:
        """Check if a local LLM provider is online"""
        settings = SettingsService.get_instance()

        if provider == "ollama":
            url = settings.get("ollama_base_url", "http://localhost:11434")

            # Only swap for Docker if actually running in Docker
            if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
                url = url.replace("localhost", "host.docker.internal").replace(
                    "127.0.0.1", "host.docker.internal"
                )

            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{url}/api/tags")
                    healthy = resp.status_code == 200
                    self._local_health["ollama"] = healthy
                    return healthy
            except Exception:
                self._local_health["ollama"] = False
                return False

        elif provider == "lmstudio":
            url = settings.get("lmstudio_base_url", "http://localhost:1234/v1")
            url = url.rstrip("/")
            if not url.endswith("/v1"):
                url = f"{url}/v1"

            # Only swap for Docker if actually running in Docker
            if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
                url = url.replace("localhost", "host.docker.internal").replace(
                    "127.0.0.1", "host.docker.internal"
                )

            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{url}/models")
                    healthy = resp.status_code == 200
                    self._local_health["lmstudio"] = healthy
                    return healthy
            except Exception:
                self._local_health["lmstudio"] = False
                return False

        return True  # Cloud providers assumed always healthy

    def get_provider_for_agent(self, agent_name: str) -> str:
        """Get the preferred LLM provider for a specific agent"""
        provider = self.agent_routing.get(agent_name, self.fallback_provider)
        logger.debug("Agent routed", agent=agent_name, provider=provider)
        return provider

    async def get_provider_with_fallback(self, agent_name: str) -> Tuple[str, bool]:
        """
        Get provider with local-first fallback.
        Returns (provider, used_fallback).

        If assigned to local → check health → fallback to cloud if offline.
        """
        preferred = self.get_provider_for_agent(agent_name)

        if preferred in LOCAL_PROVIDERS:
            is_healthy = await self.check_local_health(preferred)
            if is_healthy:
                logger.info("Using local LLM", agent=agent_name, provider=preferred)
                return preferred, False
            else:
                logger.warning(
                    "Local LLM offline, falling back to cloud",
                    agent=agent_name,
                    attempted=preferred,
                    fallback=self.cloud_fallback,
                )
                return self.cloud_fallback, True

        return preferred, False

    def get_provider_for_task(self, task_type: str) -> str:
        """Get the LLM provider for a task type"""
        return TASK_TYPE_ROUTING.get(task_type.lower(), self.fallback_provider)

    def get_client_for_agent(self, agent_name: str):
        """Get an initialized LLM client for a specific agent (sync version)"""
        from app.core.llm import get_llm_client

        provider = self.get_provider_for_agent(agent_name)

        # Quick sync health check for local providers
        if provider in LOCAL_PROVIDERS:
            cached = self._local_health.get(provider)
            if cached is False:
                logger.info(
                    "Local LLM cached as offline, using cloud", agent=agent_name
                )
                provider = self.cloud_fallback

        return get_llm_client(provider)

    def get_routing_table(self) -> Dict[str, str]:
        """Return the full routing table with health status"""
        return dict(self.agent_routing)

    def get_routing_table_with_health(self) -> Dict[str, dict]:
        """Return routing table with provider health info"""
        result = {}
        for agent, provider in self.agent_routing.items():
            is_local = provider in LOCAL_PROVIDERS
            healthy = self._local_health.get(provider, True) if is_local else True
            result[agent] = {
                "provider": provider,
                "is_local": is_local,
                "is_healthy": healthy,
                "fallback": (self.cloud_fallback if is_local and not healthy else None),
            }
        return result


# Singleton
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the model router singleton"""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
