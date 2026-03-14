"""
DealForge Domain Skills Library

This module manages loading and injecting "Skill Documents" into agents.
Inspired by Anthropic's financial-services-plugins approach:
Each skill is a Markdown file that encodes domain expertise, correct patterns,
common mistakes, and step-by-step workflows for specific financial analyses.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger()

# Mapping of task keywords/types to skill filenames
SKILL_MAP: dict[str, str] = {
    # DCF / Valuation
    "dcf": "dcf_model.md",
    "discounted cash flow": "dcf_model.md",
    "wacc": "dcf_model.md",
    "terminal value": "dcf_model.md",
    "intrinsic value": "dcf_model.md",
    # LBO
    "lbo": "lbo_model.md",
    "leveraged buyout": "lbo_model.md",
    "irr": "lbo_model.md",
    "moic": "lbo_model.md",
    "debt waterfall": "lbo_model.md",
    # Comparable Companies
    "comps": "comps_analysis.md",
    "comparable companies": "comps_analysis.md",
    "trading multiples": "comps_analysis.md",
    "ev/ebitda": "comps_analysis.md",
    "precedent transactions": "comps_analysis.md",
    # IC Memo
    "ic memo": "ic_memo.md",
    "investment committee": "ic_memo.md",
    "deal memo": "ic_memo.md",
    "recommendation memo": "ic_memo.md",
    "investment memo": "ic_memo.md",
    # Due Diligence
    "due diligence": "dd_checklist.md",
    "dd checklist": "dd_checklist.md",
    "commercial due diligence": "dd_checklist.md",
    # Risk Assessment
    "risk": "risk_assessment.md",
    "sensitivity analysis": "risk_assessment.md",
    "risk heatmap": "risk_assessment.md",
    # 3-Statement Model
    "3-statement": "three_statement_model.md",
    "three statement": "three_statement_model.md",
    "financial model": "three_statement_model.md",
    "income statement": "three_statement_model.md",
    # Market Research
    "market research": "market_research.md",
    "competitive analysis": "market_research.md",
    "tam": "market_research.md",
    "industry analysis": "market_research.md",
}

SKILLS_DIR = Path(__file__).parent / "documents"


def get_skill_for_task(task_description: str) -> Optional[str]:
    """
    Match a task description to a skill document.
    Returns the Markdown content of the skill, or None if no match.
    """
    task_lower = task_description.lower()
    for keyword, skill_file in SKILL_MAP.items():
        if keyword in task_lower:
            return _load_skill(skill_file)
    return None


def get_skill_by_name(skill_name: str) -> Optional[str]:
    """Directly load a skill by its filename."""
    return _load_skill(skill_name)


def list_available_skills() -> list[str]:
    """Return all available skill document names."""
    if not SKILLS_DIR.exists():
        return []
    return [f.name for f in SKILLS_DIR.glob("*.md")]


def _load_skill(filename: str) -> Optional[str]:
    """Load a skill Markdown file from the documents directory."""
    skill_path = SKILLS_DIR / filename
    if not skill_path.exists():
        logger.warning("skill_not_found", filename=filename, path=str(skill_path))
        return None
    try:
        content = skill_path.read_text(encoding="utf-8")
        logger.info("skill_loaded", filename=filename, size=len(content))
        return content
    except Exception as e:
        logger.error("skill_load_error", filename=filename, error=str(e))
        return None


def build_skill_context(task_description: str, agent_name: str) -> str:
    """
    Build the full skill context block to prepend to an agent's system prompt.
    This is the primary interface used by agents and the Scrum Master.
    """
    skill_content = get_skill_for_task(task_description)
    if not skill_content:
        return ""

    return f"""
## 📚 INSTITUTIONAL SKILL REFERENCE

The following domain expertise document must be strictly followed for this task.
Adhere to all <correct_patterns> and avoid all <common_mistakes> defined below.

---

{skill_content}

---
## END SKILL REFERENCE
Execute the task above while rigorously following these institutional standards.
"""
