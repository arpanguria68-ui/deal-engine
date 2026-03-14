"""
OFAS Sector Loader

Loads YAML-based sector configurations to dynamically adjust agent behavior,
tool weightings, checklists, and custom prompts based on the target's industry.
"""

import os
import yaml
import structlog
from typing import Dict, Any

logger = structlog.get_logger(__name__)

SECTOR_ADAPTERS_DIR = os.path.join(os.path.dirname(__file__), "sector_adapters")


def load_sector_config(sector_name: str) -> Dict[str, Any]:
    """
    Loads sector configuration. Returns an empty dict if adapter isn't found
    or if an error occurs during loading, allowing graceful fallback to default behaviors.
    """
    if not sector_name:
        return {}

    safe_name = sector_name.lower().strip()
    file_path = os.path.join(SECTOR_ADAPTERS_DIR, f"{safe_name}.yaml")

    if not os.path.exists(file_path):
        logger.warning(
            f"Sector adapter for '{safe_name}' not found. Using default OFAS behavior."
        )
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            logger.info("loaded_sector_adapter", sector=safe_name)
            return config or {}
    except Exception as e:
        logger.error("sector_loader_error", sector=safe_name, error=str(e))
        return {}


def build_sector_prompt(agent_name: str, sector_config: Dict[str, Any]) -> str:
    """
    Constructs an additional sector-specific prompt string for a given agent
    if the sector configuration specifies one.
    """
    if not sector_config:
        return ""

    custom_prompts = sector_config.get("custom_prompts", {})
    agent_prompt = custom_prompts.get(agent_name, "")

    sector_name = sector_config.get("sector", "unknown").capitalize()

    prompt_injection = f"\n\n--- SECTOR FOCUS: {sector_name} ---\n"
    if agent_prompt:
        prompt_injection += f"Custom Instruction: {agent_prompt}\n"

    checklists = sector_config.get("checklists", [])
    if checklists:
        prompt_injection += "Key Sector Diligence Items to consider:\n"
        for item in checklists:
            prompt_injection += f"- {item}\n"

    # Include emphasis weights if this agent is explicitly weighted
    emphasis = sector_config.get("emphasis", [])
    agent_weight = 1.0
    for e in emphasis:
        if e.get("agent") == agent_name:
            agent_weight = e.get("weight", 1.0)
            break

    if agent_weight > 1.0:
        prompt_injection += "\nNOTE: Your role is highly emphasized for this sector. Please provide extremely detailed analysis."

    return prompt_injection
