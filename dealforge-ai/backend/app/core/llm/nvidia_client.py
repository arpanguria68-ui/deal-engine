"""NVIDIA LLM Client — OpenAI-compatible interface for NVIDIA API Bridge."""

from typing import List, Dict, Any, Optional
import json
import os
import structlog
from app.config import get_settings

logger = structlog.get_logger()


class NvidiaClient:
    """Client for NVIDIA API Bridge (OpenAI-compatible)"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        from openai import AsyncOpenAI

        settings = get_settings()

        self.base_url = base_url or getattr(
            settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.api_key = api_key or getattr(settings, "NVIDIA_API_KEY", None) or os.environ.get("NVIDIA_API_KEY") or "placeholder_key"
        self.model = model or getattr(settings, "NVIDIA_MODEL", "z-ai/glm5")

        # Initialize AsyncOpenAI with NVIDIA URL and key
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        self.provider = "nvidia"
        self.max_context = 16384

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate using NVIDIA API"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        # Base parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 1.0),
            "top_p": kwargs.get("top_p", 1.0),
            "max_tokens": kwargs.get("max_tokens", 16384),
            "seed": 42,
            "stream": False,
        }

        # NVIDIA specific kwargs (e.g., thinking mode for glm5)
        # Wrap them in extra_body for AsyncOpenAI to pass them through
        if "z-ai/glm5" in self.model:
            params["extra_body"] = {
                "chat_template_kwargs": {
                    "enable_thinking": True,
                    "clear_thinking": False
                }
            }

        # Handle tools if provided
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**params)
            message = response.choices[0].message

            result = {
                "content": message.content or "", 
                "raw_response": response.model_dump() if hasattr(response, "model_dump") else str(response)
            }

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
                "NVIDIA API call failed",
                error=str(e),
                model=self.model
            )
            raise
