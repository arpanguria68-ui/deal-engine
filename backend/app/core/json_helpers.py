import json
import re
import structlog
from typing import Dict, Any, Union

logger = structlog.get_logger()


def extract_and_parse_json(content: str) -> Union[Dict[str, Any], list, str]:
    """
    Robustly extract and parse JSON from LLM outputs, especially local LLMs
    which often append conversational text or trailing commas.
    Also strips <think> blocks from reasoning models.
    """
    if not content:
        return {}

    # Strip reasoning tags (DeepSeek R1 etc)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)

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
        start_dict = json_str.find("{")
        end_dict = json_str.rfind("}")

        start_list = json_str.find("[")
        end_list = json_str.rfind("]")

        # Determine if it's more likely a list or dict based on boundaries
        if (
            start_list != -1
            and end_list > start_list
            and (start_dict == -1 or start_list < start_dict)
        ):
            clean_str = json_str[start_list : end_list + 1]
            try:
                return json.loads(clean_str)
            except json.JSONDecodeError:
                pass

        if start_dict != -1 and end_dict > start_dict:
            clean_str = json_str[start_dict : end_dict + 1]
            try:
                return json.loads(clean_str)
            except json.JSONDecodeError:
                pass

        logger.error("json_parse_failed", error=str(e), raw_snippet=json_str[:200])
        # DealForge 2.0: If JSON parsing fails entirely, do not swallow the content.
        # Return it as reasoning so it appears in the final report instead of "No analysis".
        return {"reasoning": content}
