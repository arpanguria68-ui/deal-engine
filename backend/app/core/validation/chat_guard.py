"""
Prompt guardrails for endpoints that send user text to an LLM.

Checks, in order:
* non-empty string, within MAX_PROMPT_LENGTH (hard limit, not a warning)
* no control characters (NUL etc.)
* no prompt-injection / secret-exfiltration attempts — e.g. "ignore previous
  instructions", "reveal your system prompt", "print the API key"

The previous version blocked plain words such as "attack", "exploit", "hack"
and "virus". In an M&A tool those are routine ("exploit synergies", "hostile
takeover attack", "cyber-attack exposure", "virus diagnostics target"), so
they rejected legitimate diligence questions; they are no longer blocked.

Rejected prompts are logged by length and hash only — deal prompts carry
confidential information and must not be copied into logs.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import List, Optional

import structlog

logger = structlog.get_logger()

MAX_PROMPT_LENGTH = int(os.environ.get("DEALFORGE_MAX_PROMPT_CHARS", "8000"))
WARN_PROMPT_LENGTH = 4000

# Attempts to override the system's instructions or extract secrets.
INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b"
        r"(?:previous|prior|above|earlier|all|system|your)\b[^.\n]{0,20}\b"
        r"(?:instructions?|prompts?|rules?|guidelines?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|print|show|output|repeat|leak|dump)\b[^.\n]{0,30}\b"
        r"(?:system\s+prompt|hidden\s+instructions?|initial\s+instructions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|print|show|output|leak|dump|give\s+me)\b[^.\n]{0,30}\b"
        r"(?:api[\s_-]?keys?|secret\s+keys?|access\s+tokens?|passwords?|credentials|"
        r"env(?:ironment)?\s+variables?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:you\s+are\s+now|act\s+as)\s+(?:DAN|an?\s+unrestricted)\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
]

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12]


def check_prompt(prompt: str, max_length: Optional[int] = None) -> dict:
    """Run guardrail checks on a user prompt.

    Returns a dict with keys:
        valid: bool  -- whether the prompt passed all checks
        errors: List[str]  -- list of human-readable error messages
        warnings: List[str]  -- optional warnings (e.g. long prompt)
    """
    errors: List[str] = []
    warnings: List[str] = []
    limit = max_length or MAX_PROMPT_LENGTH

    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("Prompt must be a non-empty string.")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if len(prompt) > limit:
        errors.append(f"Prompt is {len(prompt)} characters; the limit is {limit}.")
    elif len(prompt) > WARN_PROMPT_LENGTH:
        warnings.append(f"Long prompt ({len(prompt)} characters).")

    if _CONTROL_CHARS.search(prompt):
        errors.append("Prompt contains control characters.")

    for pat in INJECTION_PATTERNS:
        if pat.search(prompt):
            errors.append(
                "Prompt looks like an attempt to override system instructions "
                "or extract secrets."
            )
            break

    if errors:
        logger.warning(
            "prompt_guard_failed",
            length=len(prompt),
            fingerprint=_fingerprint(prompt),
            errors=errors,
        )
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def enforce_prompts(*prompts: Optional[str], max_length: Optional[int] = None) -> None:
    """Raise HTTP 400 if any non-empty prompt fails check_prompt().

    For endpoints that pass user text straight to an LLM or agent.
    """
    from fastapi import HTTPException

    for prompt in prompts:
        if prompt is None or prompt == "":
            continue
        result = check_prompt(prompt, max_length=max_length)
        if not result["valid"]:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_prompt", "details": result},
            )

