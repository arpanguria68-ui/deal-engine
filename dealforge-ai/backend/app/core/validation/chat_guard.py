"""
Simple guardrail utilities for chat endpoints.

These helpers can be used prior to sending prompts to the LLM so that we
reject or sanitise unsafe input early.  Eventually we may call a model
moderation API (OpenAI, Gemini, etc.), but for now we include a few
basic checks:

* maximum prompt length
* disallowed keywords (e.g. profanity, destructive requests)
* rate limiting placeholder (could be integrated with FastAPI dependency)

Other modules in the project (like `output_validator`) follow a similar
pattern; chat endpoints import and use these helpers.
"""
from __future__ import annotations

import re
import structlog
from typing import List

logger = structlog.get_logger()

# list of words/phrases that will trigger a rejection
DISALLOWED_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(?:suicide|self[- ]harm|attack)\b", re.IGNORECASE),
    re.compile(r"\b(?:hack|exploit|virus)\b", re.IGNORECASE),
    # add other terms as needed
]

MAX_PROMPT_LENGTH = 2000  # characters


def check_prompt(prompt: str) -> dict:
    """Run guardrail checks on a user prompt.

    Returns a dict with keys:
        valid: bool  -- whether the prompt passed all checks
        errors: List[str]  -- list of human-readable error messages
        warnings: List[str]  -- optional warnings (e.g. over length)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("Prompt must be a non-empty string.")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if len(prompt) > MAX_PROMPT_LENGTH:
        warnings.append(
            f"Prompt length ({len(prompt)}) exceeds {MAX_PROMPT_LENGTH} characters."
        )

    for pat in DISALLOWED_PATTERNS:
        if pat.search(prompt):
            errors.append(f"Prompt contains disallowed content: `{pat.pattern}`")

    if errors:
        logger.warning("prompt_guard_failed", prompt=prompt, errors=errors)
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
