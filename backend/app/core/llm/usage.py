"""Normalise provider token-usage reports to {"input_tokens", "output_tokens"}."""

from typing import Any, Dict, Optional


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def usage_from_openai(response: Any) -> Optional[Dict[str, int]]:
    """OpenAI-compatible SDK responses (OpenAI, LM Studio, NVIDIA, Mistral)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    inp = _as_int(getattr(usage, "prompt_tokens", None))
    out = _as_int(getattr(usage, "completion_tokens", None))
    if inp is None and out is None:
        return None
    return {"input_tokens": inp or 0, "output_tokens": out or 0}


def usage_from_gemini(response: Any) -> Optional[Dict[str, int]]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None
    inp = _as_int(getattr(meta, "prompt_token_count", None))
    out = _as_int(getattr(meta, "candidates_token_count", None))
    if inp is None and out is None:
        return None
    return {"input_tokens": inp or 0, "output_tokens": out or 0}


def usage_from_ollama(data: Dict[str, Any]) -> Optional[Dict[str, int]]:
    inp = _as_int(data.get("prompt_eval_count"))
    out = _as_int(data.get("eval_count"))
    if inp is None and out is None:
        return None
    return {"input_tokens": inp or 0, "output_tokens": out or 0}
