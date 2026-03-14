"""
Question Quality Store — Lightweight RL Signal for Scrum Master

Tracks which clarification question types led to high-quality agent outputs
(based on confidence scores from the ScoringAgent). Over time, high-scoring
question types are surfaced first in the LLM prompt.

This is Tier 3 of the Intelligent Scrum Master upgrade.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import structlog

logger = structlog.get_logger()

_QUALITY_DIR = (
    Path(__file__).parent.parent.parent.parent / "pageindex_data" / "question_quality"
)


def _get_quality_file(deal_type: str) -> Path:
    _QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    safe_key = deal_type.lower().replace(" ", "_")[:40]
    return _QUALITY_DIR / f"{safe_key}_quality.json"


def _load_quality(deal_type: str) -> Dict[str, Any]:
    path = _get_quality_file(deal_type)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(
                "question_quality_load_error", deal_type=deal_type, error=str(e)
            )
    return {"by_type": {}, "outcomes": []}


def _save_quality(deal_type: str, data: Dict[str, Any]) -> None:
    path = _get_quality_file(deal_type)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("question_quality_save_error", deal_type=deal_type, error=str(e))


class QuestionQualityStore:
    """
    Lightweight RL-signal store that learns which clarification questions
    lead to better agent outputs over time.

    Uses exponential moving average (EMA) of task scores per question type.
    """

    EMA_ALPHA = 0.3  # Weight to give to new observations vs history

    def record_outcome(
        self,
        deal_type: str,
        question_types_asked: List[str],
        task_score: float,
        user_rated_plan: Optional[str] = None,
    ) -> None:
        """
        Record the deal outcome (agent confidence score + optional user rating)
        for a particular set of question types.

        Args:
            deal_type: Type of deal
            question_types_asked: List of question type strings that were asked
            task_score: Final average confidence score from agents (0.0 to 1.0)
            user_rated_plan: Optional user rating: "positive", "negative", or None
        """
        data = _load_quality(deal_type)

        # Apply user rating boost/penalty
        effective_score = task_score
        if user_rated_plan == "positive":
            effective_score = min(1.0, task_score + 0.15)
        elif user_rated_plan == "negative":
            effective_score = max(0.0, task_score - 0.15)

        for qt in question_types_asked:
            if qt not in data["by_type"]:
                data["by_type"][qt] = {"ema_score": effective_score, "n": 1}
            else:
                old = data["by_type"][qt]["ema_score"]
                new_ema = self.EMA_ALPHA * effective_score + (1 - self.EMA_ALPHA) * old
                data["by_type"][qt]["ema_score"] = round(new_ema, 4)
                data["by_type"][qt]["n"] += 1

        data["outcomes"].append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "question_types": question_types_asked,
                "task_score": task_score,
                "effective_score": effective_score,
                "user_rating": user_rated_plan,
            }
        )
        # keep only last 50 outcomes
        data["outcomes"] = data["outcomes"][-50:]

        _save_quality(deal_type, data)
        logger.info(
            "question_quality_recorded",
            deal_type=deal_type,
            qtypes=question_types_asked,
            score=effective_score,
        )

    def get_top_questions(self, deal_type: str, max_n: int = 3) -> List[str]:
        """
        Return the question types most correlated with high-quality outcomes.
        These are injected into the LLM prompt to prioritize historically useful questions.

        Args:
            deal_type: Type of deal
            max_n: Max items to return

        Returns:
            List of question type strings, sorted by EMA score descending
        """
        data = _load_quality(deal_type)
        by_type = data.get("by_type", {})

        # Only include types with at least 2 observations (avoids noise)
        scored = [
            (qt, stats["ema_score"])
            for qt, stats in by_type.items()
            if stats.get("n", 0) >= 2
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [qt for qt, _ in scored[:max_n]]

    def get_summary_for_prompt(self, deal_type: str) -> str:
        """
        Return a formatted string for LLM injection that describes
        which question types have historically led to the best outcomes.
        """
        top = self.get_top_questions(deal_type, max_n=3)
        if not top:
            return ""
        types_str = ", ".join(top)
        return (
            f"HISTORICALLY MOST VALUABLE question types for {deal_type} deals: [{types_str}]. "
            f"Prioritize these in your questions.\n"
        )
