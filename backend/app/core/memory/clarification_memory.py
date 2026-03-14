"""
Clarification Memory — Self-Learning Q&A Store

Stores and retrieves prior clarification Q&A pairs to avoid re-asking
resolved questions in future sessions. Keyed by deal_type.

This is Tier 2 of the Intelligent Scrum Master upgrade.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import structlog

logger = structlog.get_logger()

# Storage location
_MEMORY_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "pageindex_data"
    / "clarification_memory"
)


def _get_memory_file(deal_type: str) -> Path:
    """Return the JSON file path for a given deal type."""
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    safe_key = deal_type.lower().replace(" ", "_").replace("/", "_")[:40]
    return _MEMORY_DIR / f"{safe_key}.json"


def _load_memory(deal_type: str) -> Dict[str, Any]:
    path = _get_memory_file(deal_type)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(
                "clarification_memory_load_error", deal_type=deal_type, error=str(e)
            )
    return {"qa_pairs": [], "summary": ""}


def _save_memory(deal_type: str, data: Dict[str, Any]) -> None:
    path = _get_memory_file(deal_type)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(
            "clarification_memory_save_error", deal_type=deal_type, error=str(e)
        )


class ClarificationMemory:
    """
    Persists clarification Q&A pairs per deal type.
    On future sessions, injects prior answers into the Scrum Master prompt
    so it doesn't re-ask already-resolved questions.
    """

    def store(self, deal_type: str, questions: List[Dict], answers: str) -> None:
        """
        Store a resolved clarification exchange.

        Args:
            deal_type: Type of deal e.g. "m&a", "valuation", "lbo"
            questions: List of question dicts that were asked
            answers: The user's combined answer string
        """
        data = _load_memory(deal_type)
        pair = {
            "timestamp": datetime.utcnow().isoformat(),
            "questions": [q.get("question", "") for q in questions],
            "question_types": [q.get("type", "unknown") for q in questions],
            "user_answer": answers,
        }
        data["qa_pairs"].append(pair)
        # Keep only the last 20 exchanges to avoid memory bloat
        data["qa_pairs"] = data["qa_pairs"][-20:]
        _save_memory(deal_type, data)
        logger.info(
            "clarification_memory_stored",
            deal_type=deal_type,
            n_questions=len(questions),
        )

    def lookup(self, deal_type: str, question_type: str) -> Optional[str]:
        """
        Look up a prior answer for a question type in a given deal type.

        Args:
            deal_type: Type of deal
            question_type: e.g. "constraint", "objective", "data_availability"

        Returns:
            The most recent matching user answer, or None
        """
        data = _load_memory(deal_type)
        # Most recent first
        for pair in reversed(data["qa_pairs"]):
            if question_type in pair.get("question_types", []):
                return pair["user_answer"]
        return None

    def get_context_for_prompt(self, deal_type: str, prompt: str) -> str:
        """
        Build a prior-context string to inject into the LLM prompt.
        Tells the LLM what the user already answered so it won't re-ask.

        Args:
            deal_type: Auto-detected deal type
            prompt: Current user prompt (for relevance check)

        Returns:
            A formatted string suitable for LLM injection, or empty string
        """
        data = _load_memory(deal_type)
        if not data["qa_pairs"]:
            return ""

        # Aggregate the most recent answers per unique question type
        seen_types: set = set()
        prior_lines: List[str] = []
        for pair in reversed(data["qa_pairs"]):
            for (
                qt,
                q,
            ) in zip(pair.get("question_types", []), pair.get("questions", [])):
                if qt not in seen_types:
                    seen_types.add(qt)
                    # Quote a short version of question + answer
                    q_short = q[:120] + ("..." if len(q) > 120 else "")
                    a_short = pair["user_answer"][:200] + (
                        "..." if len(pair["user_answer"]) > 200 else ""
                    )
                    prior_lines.append(f'- ({qt}) "{q_short}" → "{a_short}"')

        if not prior_lines:
            return ""

        lines_text = "\n".join(prior_lines[:6])  # Max 6 prior items
        return (
            f"PRIOR CONTEXT (from memory — do NOT re-ask unless the new prompt contradicts these):\n"
            f"{lines_text}\n"
        )

    def detect_deal_type(self, prompt: str) -> str:
        """
        Detect the deal type from the prompt string for memory keying.

        Returns:
            One of: "m_a", "lbo", "ipo", "valuation", "due_diligence", "general"
        """
        p = prompt.lower()
        if any(
            kw in p
            for kw in ["acquisition", "merger", "m&a", "takeover", "buyout", "acquire"]
        ):
            return "m_a"
        if "lbo" in p or "leveraged" in p:
            return "lbo"
        if "ipo" in p or "public offering" in p:
            return "ipo"
        if "valuation" in p or "dcf" in p or "multiple" in p or "comparable" in p:
            return "valuation"
        if "due diligence" in p or "dd " in p:
            return "due_diligence"
        return "general"
