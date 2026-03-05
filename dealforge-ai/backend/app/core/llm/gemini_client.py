"""Gemini LLM Client"""

import google.generativeai as genai
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
import structlog
from app.config import get_settings

logger = structlog.get_logger()


class GeminiClient:
    """Client for Google's Gemini API"""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model or settings.GEMINI_MODEL

        if self.api_key:
            genai.configure(api_key=self.api_key)
        else:
            logger.warning("Gemini API key not configured")

    def _get_model(self, tools: Optional[List[Dict]] = None):
        """Get configured model instance"""
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }

        if tools:
            # Transform OpenAI-style tools to Gemini format
            # Gemini expects a list of FunctionDeclarations with specific schema rules
            formatted_tools = []
            for tool in tools:
                if isinstance(tool, dict):
                    if tool.get("type") == "function" and "function" in tool:
                        # Extract the function part
                        func = dict(tool["function"])
                    else:
                        func = dict(tool)

                    # Ensure no invalid fields like 'type' or 'strict' are in the declaration
                    func.pop("type", None)
                    func.pop("strict", None)

                    # Recursively fix types in parameters (Gemini expects uppercase: 'OBJECT', 'STRING')
                    if "parameters" in func and isinstance(func["parameters"], dict):
                        func["parameters"] = self._fix_schema(func["parameters"])

                    formatted_tools.append(func)
                else:
                    formatted_tools.append(tool)

            # Enable function calling
            return genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                tools=formatted_tools,
            )

        return genai.GenerativeModel(
            model_name=self.model_name, generation_config=generation_config
        )

    def _fix_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively fix JSON schema for Gemini compatibility"""
        if not isinstance(schema, dict):
            return schema

        new_schema = dict(schema)

        # 1. Gemini expects uppercase types (STRING, NUMBER, INTEGER, BOOLEAN, ARRAY, OBJECT)
        if "type" in new_schema and isinstance(new_schema["type"], str):
            new_schema["type"] = new_schema["type"].upper()

        # 2. Remove unsupported fields (Gemini Schema is strict)
        # These fields cause "ValueError: Unknown field for Schema"
        unsupported_fields = [
            "default",
            "title",
            "examples",
            "example",
            "allOf",
            "anyOf",
            "oneOf",
        ]
        for field in unsupported_fields:
            new_schema.pop(field, None)

        # 3. Recursively fix properties
        if "properties" in new_schema and isinstance(new_schema["properties"], dict):
            new_schema["properties"] = {
                k: self._fix_schema(v) for k, v in new_schema["properties"].items()
            }

        # 4. Recursively fix items (for arrays)
        if "items" in new_schema and isinstance(new_schema["items"], dict):
            new_schema["items"] = self._fix_schema(new_schema["items"])

        return new_schema

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Generate text using Gemini

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature

        Returns:
            Response dict with content and optional tool calls
        """
        try:
            model = self._get_model(tools)

            # Build conversation
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            else:
                full_prompt = prompt

            logger.debug("Gemini generation request", prompt_length=len(full_prompt))

            response = await model.generate_content_async(full_prompt)

            # Extract text content safely
            content = ""
            try:
                content = response.text or ""
            except ValueError:
                pass

            # Check for function calls
            function_calls = []
            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call"):
                                function_calls.append(
                                    {
                                        "name": part.function_call.name,
                                        "args": (
                                            dict(part.function_call.args)
                                            if part.function_call.args
                                            else {}
                                        ),
                                    }
                                )

            return {
                "content": content,
                "function_calls": function_calls,
                "raw_response": response,
            }

        except Exception as e:
            logger.error("Gemini generation failed", error=str(e))
            raise

    async def generate_stream(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream generation from Gemini

        Args:
            prompt: User prompt
            system_prompt: Optional system instructions

        Yields:
            Text chunks as they are generated
        """
        try:
            model = self._get_model()

            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            else:
                full_prompt = prompt

            response = await model.generate_content_async(full_prompt, stream=True)

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error("Gemini stream generation failed", error=str(e))
            raise

    async def generate_structured(
        self,
        prompt: str,
        output_schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output

        Args:
            prompt: User prompt
            output_schema: JSON schema for expected output
            system_prompt: Optional system instructions

        Returns:
            Parsed JSON response
        """
        schema_prompt = f"""
{prompt}

You must respond with valid JSON matching this schema:
{json.dumps(output_schema, indent=2)}

Respond ONLY with the JSON, no other text.
"""

        response = await self.generate(schema_prompt, system_prompt)
        content = response["content"]

        # Extract JSON from response
        try:
            # Try to find JSON in code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                json_str = content.strip()

            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse structured output", content=content, error=str(e)
            )
            raise


class OpenAIClient:
    """Client for OpenAI API (GPT-4, Codex)"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from openai import AsyncOpenAI

        settings = get_settings()
        self.client = AsyncOpenAI(api_key=api_key or settings.OPENAI_API_KEY)
        self.model = model or settings.OPENAI_MODEL

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate using OpenAI"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**params)

        message = response.choices[0].message

        result = {"content": message.content or "", "raw_response": response}

        if message.tool_calls:
            result["function_calls"] = [
                {"name": tc.function.name, "args": json.loads(tc.function.arguments)}
                for tc in message.tool_calls
            ]

        return result

    async def generate_code(self, prompt: str, language: str = "python") -> str:
        """Generate code using Codex model"""
        settings = get_settings()

        code_prompt = f"""Generate {language} code for the following:

{prompt}

Provide only the code, no explanations."""

        response = await self.client.chat.completions.create(
            model=settings.CODEX_MODEL,
            messages=[{"role": "user", "content": code_prompt}],
            temperature=0.2,
            max_tokens=4000,
        )

        return response.choices[0].message.content


class MistralClient:
    """Client for Mistral API using official SDK"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from mistralai import Mistral

        settings = get_settings()
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = model or settings.MISTRAL_MODEL
        self.client = Mistral(api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate using Mistral SDK"""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        params = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        response = await self.client.chat.complete_async(**params)

        message = response.choices[0].message

        result = {"content": message.content or "", "raw_response": response}

        if message.tool_calls:
            result["function_calls"] = [
                {
                    "name": tc.function.name,
                    "args": (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    ),
                }
                for tc in message.tool_calls
            ]

        return result
