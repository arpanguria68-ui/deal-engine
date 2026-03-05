import json
import re
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


def extract_and_parse_json(content: str) -> Dict[str, Any]:
    """
    Robustly extract and parse JSON from LLM outputs, especially local LLMs
    which often append conversational text or trailing commas.
    """
    if not content:
        return {}

    # Extract JSON block
    if "```json" in content:
        json_str = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        json_str = content.split("```")[1].split("```")[0].strip()
    else:
        json_str = content.strip()

    # Clean local LLM artifacts
    # 1. Remove trailing commas before closing braces/brackets
    json_str = re.sub(r",\s*}", "}", json_str)
    json_str = re.sub(r",\s*\]", "]", json_str)
    # 2. Sometimes LLMs output a python dictionary with single quotes.
    # Be careful not to replace inner apostrophes, but this regex tries to fix quotes around keys.
    json_str = re.sub(r"(?<!\\)'(\w+)'\s*:", r'"\1":', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback: substring extraction
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start != -1 and end != -1 and end > start:
            clean_str = json_str[start : end + 1]
            try:
                return json.loads(clean_str)
            except json.JSONDecodeError:
                pass

        logger.error("json_parse_failed", error=str(e), raw_snippet=json_str[:200])
        # DealForge 2.0: If JSON parsing fails entirely, do not swallow the content.
        # Return it as reasoning so it appears in the final report instead of "No analysis".
        return {"reasoning": content}
