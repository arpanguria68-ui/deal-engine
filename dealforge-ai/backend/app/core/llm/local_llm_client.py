"""Local LLM Clients (Ollama & LM Studio)"""

from typing import List, Dict, Any, Optional, AsyncGenerator
import json
import httpx
import structlog
from app.config import get_settings

logger = structlog.get_logger()


class OllamaClient:
    """Client for local Ollama instances"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        settings = get_settings()
        url = base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")

        import os

        if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
            url = url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )

        self.base_url = url.rstrip("/")
        self.model = model or getattr(settings, "OLLAMA_MODEL", "llama3")
        self.client = httpx.AsyncClient(timeout=120.0)
        self.provider = "ollama"
        self.max_context = 8000

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate using Ollama Chat API"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
            },
        }

        # Note: Ollama supports experimental tools, but we'll focus on text gen for now
        # or pass them if the model supports it.
        if tools:
            # Format generic JSON schema tools to Ollama's expected format (which matches OpenAI)
            payload["tools"] = tools

        try:
            response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            message = data.get("message", {})
            content = message.get("content", "")

            result = {"content": content, "raw_response": data}

            # Handle Ollama tool calls if present
            if message.get("tool_calls"):
                result["function_calls"] = [
                    {
                        "name": tc["function"]["name"],
                        "args": tc["function"]["arguments"],
                    }
                    for tc in message["tool_calls"]
                ]

            return result

        except httpx.HTTPError as e:
            logger.error("Ollama connection failed. Is Ollama running?", error=str(e))
            raise


class LMStudioClient:
    """Client for local LM Studio instances (OpenAI-compatible)"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        from openai import AsyncOpenAI

        settings = get_settings()

        url = base_url or getattr(
            settings, "LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
        )
        url = url.rstrip("/")
        if not url.endswith("/v1"):
            url = f"{url}/v1"

        import os

        if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
            url = url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )

        self.base_url = url
        # Model name often doesn't matter for LM Studio as it uses the loaded model, but we pass it anyway
        self.model = model or getattr(settings, "LMSTUDIO_MODEL", "local-model")

        # Initialize AsyncOpenAI with local LM Studio URL and dummy key
        self.client = AsyncOpenAI(base_url=self.base_url, api_key="lm-studio")
        self.provider = "lmstudio"
        self.max_context = 12000

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate using LM Studio Local Inference Server"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 12000),
        }

        # Note: Many local models in LM Studio don't support tool calling natively,
        # but we pass them if provided.
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**params)
            message = response.choices[0].message

            result = {"content": message.content or "", "raw_response": response}

            if message.tool_calls:
                result["function_calls"] = [
                    {
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments),
                    }
                    for tc in message.tool_calls
                ]

            return result

        except Exception as e:
            logger.error(
                "LM Studio connection failed. Is the Local Server running?",
                error=str(e),
            )
            raise
