"""
SEC Filing Due Diligence Tool — NLP Change Detection & Financial Impact Prediction

Based on "Predicting Firm Financial Performance from SEC Filing Changes"
(Gupta, Rawte, & Zaki, 2023).

Features:
- 10-K and 8-K filing comparison via TF-IDF cosine similarity
- Loughran-McDonald financial sentiment scoring
- Fog index (readability) tracking
- Abnormal change flagging with region-aware thresholds (US/India/EU)
- 8-K event clustering via DBSCAN temporal grouping
- Kernel Ridge Regression for ROA/ROE shift prediction
"""

import json
import re
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.kernel_ridge import KernelRidge
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
from sklearn.cluster import DBSCAN

from app.core.tools.tool_router import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
#  Loughran-McDonald Financial Sentiment Dictionary
# ═══════════════════════════════════════════════

LM_NEGATIVE = {
    "litigation",
    "impairment",
    "risk",
    "loss",
    "decline",
    "challenge",
    "threat",
    "breach",
    "penalty",
    "cyber",
    "default",
    "fraud",
    "adverse",
    "terminate",
    "layoff",
    "restructuring",
    "write-off",
    "contingent",
    "uncertainty",
    "violation",
}

LM_POSITIVE = {
    "growth",
    "expansion",
    "strong",
    "improve",
    "gain",
    "success",
    "opportunity",
    "innovative",
    "profitable",
    "exceeded",
    "upgrade",
    "momentum",
    "efficiency",
    "optimistic",
    "robust",
}

# ═══════════════════════════════════════════════
#  Region-Aware Abnormality Thresholds
# ═══════════════════════════════════════════════

REGION_THRESHOLDS = {
    "US": {
        "similarity_drop_10k": 0.70,
        "similarity_drop_8k": 0.60,
        "sentiment_shift": 0.15,
        "fog_change": 2.0,
        "length_change_pct": 0.25,
        "roa_impact_threshold": 0.05,
    },
    "India": {
        "similarity_drop_10k": 0.65,
        "similarity_drop_8k": 0.55,
        "sentiment_shift": 0.12,
        "fog_change": 1.8,
        "length_change_pct": 0.30,
        "roa_impact_threshold": 0.04,
    },
    "EU": {
        "similarity_drop_10k": 0.68,
        "similarity_drop_8k": 0.58,
        "sentiment_shift": 0.13,
        "fog_change": 2.2,
        "length_change_pct": 0.28,
        "roa_impact_threshold": 0.045,
    },
}


def detect_region(ticker: str) -> str:
    """Auto-detect filing region from ticker suffix."""
    if ticker.endswith((".NS", ".BO")):
        return "India"
    if ticker.endswith((".DE", ".PA", ".L", ".AS", ".MI")):
        return "EU"
    return "US"


# ═══════════════════════════════════════════════
#  Filing Due Diligence Engine
# ═══════════════════════════════════════════════


class FilingDueDiligenceEngine:
    """
    Core NLP engine for SEC filing change detection and financial impact prediction.

    Methods:
        compute_filing_features() — Extract TF-IDF, Fog, sentiment, risk freq
        compare_filing_texts()    — Compare consecutive filing sections
        predict_financial_impact()— KRR model for ROA/ROE shift prediction
        cluster_8k_events()       — DBSCAN temporal clustering of 8-K events
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=2000, stop_words="english")
        self._train_predictor()

    def _train_predictor(self):
        """
        Train Kernel Ridge Regression on synthetic data mimicking paper parameters.

        In production, replace with real historical filing changes + actual ROA data
        from Compustat or similar.
        """
        np.random.seed(42)
        n_samples = 500
        # Features: similarity_change, sentiment_shift, fog_change, length_pct
        X = np.random.randn(n_samples, 4) * np.array([0.2, 0.15, 2.0, 0.3])
        # Target: ROA shift (paper coefficients)
        y = (
            0.08 * X[:, 0]
            - 0.12 * X[:, 1]
            + 0.005 * X[:, 2]
            - 0.06 * X[:, 3]
            + np.random.normal(0, 0.02, n_samples)
        )

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        self.predictor = KernelRidge(kernel="rbf", alpha=1.0)
        self.predictor.fit(X_train, y_train)

        train_r2 = r2_score(y_train, self.predictor.predict(X_train))
        test_r2 = r2_score(y_test, self.predictor.predict(X_test))
        logger.info(
            f"Filing DD predictor trained (R² train/test: {train_r2:.3f}/{test_r2:.3f})"
        )

    def compute_filing_features(self, text: str) -> Dict[str, float]:
        """
        Extract paper-inspired features from a single filing section.

        Returns:
            Dict with word_count, fog_index, sentiment, risk_freq.
        """
        if not text or not text.strip():
            return {
                "word_count": 0,
                "fog_index": 0.0,
                "sentiment": 0.0,
                "risk_freq": 0.0,
            }

        words = text.lower().split()
        word_count = len(words)

        # Readability — Gunning Fog index approximation
        # Split on sentence-ending punctuation
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        n_sentences = max(len(sentences), 1)

        avg_words_per_sentence = word_count / n_sentences
        complex_words = sum(
            1 for word in words if len(word) >= 3 and re.match(r"^[a-z]+$", word)
        )
        complex_pct = complex_words / word_count if word_count > 0 else 0
        fog = 0.4 * (avg_words_per_sentence + 100 * complex_pct)

        # Sentiment — Loughran-McDonald style
        neg_count = sum(1 for w in words if w in LM_NEGATIVE)
        pos_count = sum(1 for w in words if w in LM_POSITIVE)
        sentiment = (pos_count - neg_count) / word_count if word_count > 0 else 0.0

        # Risk keyword frequency
        risk_keywords = sum(
            1
            for w in words
            if w
            in {
                "litigation",
                "impairment",
                "risk",
                "loss",
                "breach",
                "penalty",
                "cyber",
            }
        )
        risk_freq = risk_keywords / word_count if word_count > 0 else 0.0

        return {
            "word_count": word_count,
            "fog_index": round(fog, 2),
            "sentiment": round(sentiment, 6),
            "risk_freq": round(risk_freq, 6),
        }

    def compare_filing_texts(
        self,
        prev_text: str,
        curr_text: str,
        section_name: str = "mda",
        form_type: str = "10-K",
        region: str = "US",
    ) -> Dict[str, Any]:
        """
        Compare two consecutive filing sections and flag abnormalities.

        Args:
            prev_text: Previous filing section text.
            curr_text: Current filing section text.
            section_name: Name of section (e.g., 'mda', 'risk_factors').
            form_type: '10-K' or '8-K'.
            region: 'US', 'India', or 'EU'.

        Returns:
            Dict with similarity, feature deltas, and abnormality flags.
        """
        if not prev_text or not curr_text:
            return {"error": "Empty text provided", "section": section_name}

        # TF-IDF cosine similarity
        try:
            tfidf_matrix = self.vectorizer.fit_transform([prev_text, curr_text])
            sim = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
        except Exception:
            sim = 0.0

        # Feature extraction
        prev_feats = self.compute_filing_features(prev_text)
        curr_feats = self.compute_filing_features(curr_text)

        # Compute deltas
        length_change_pct = (
            (curr_feats["word_count"] - prev_feats["word_count"])
            / prev_feats["word_count"]
            if prev_feats["word_count"] > 0
            else 0.0
        )
        sentiment_shift = curr_feats["sentiment"] - prev_feats["sentiment"]
        fog_change = curr_feats["fog_index"] - prev_feats["fog_index"]
        risk_freq_change = curr_feats["risk_freq"] - prev_feats["risk_freq"]

        # Get thresholds for region/form
        thresholds = REGION_THRESHOLDS.get(region, REGION_THRESHOLDS["US"])
        sim_threshold = (
            thresholds["similarity_drop_10k"]
            if form_type == "10-K"
            else thresholds["similarity_drop_8k"]
        )

        # Flag abnormalities
        flags = []
        if sim < sim_threshold:
            flags.append("Abnormal similarity drop")
        length_thresh = thresholds["length_change_pct"]
        if abs(length_change_pct) > length_thresh:
            flags.append("Abnormal length change")
        if abs(sentiment_shift) > thresholds["sentiment_shift"]:
            flags.append("Abnormal sentiment shift")
        if abs(fog_change) > thresholds["fog_change"]:
            flags.append("Abnormal readability shift")

        return {
            "section": section_name,
            "form_type": form_type,
            "region": region,
            "similarity": round(sim, 4),
            "length_change_pct": round(length_change_pct, 4),
            "sentiment_shift": round(sentiment_shift, 6),
            "fog_change": round(fog_change, 2),
            "risk_freq_change": round(risk_freq_change, 6),
            "prev_features": prev_feats,
            "curr_features": curr_feats,
            "flags": "; ".join(flags) if flags else "Normal",
            "is_abnormal": len(flags) > 0,
        }

    def predict_financial_impact(
        self,
        comparisons: List[Dict[str, Any]],
        form_type: str = "10-K",
    ) -> Dict[str, Any]:
        """
        Predict ROA/ROE shifts from filing comparison features.

        Uses Kernel Ridge Regression trained on paper-aligned synthetic data.

        Args:
            comparisons: List of compare_filing_texts() results.
            form_type: '10-K' or '8-K' (8-K gets amplified impact).

        Returns:
            Dict with predicted shifts and high-impact flags.
        """
        if not comparisons:
            return {"predictions": [], "avg_roa_shift": 0.0, "high_impact_count": 0}

        predictions = []
        for comp in comparisons:
            features = np.array(
                [
                    [
                        comp.get("similarity", 0.8),
                        comp.get("sentiment_shift", 0.0),
                        comp.get("fog_change", 0.0),
                        comp.get("length_change_pct", 0.0),
                    ]
                ]
            )

            roa_shift = float(self.predictor.predict(features)[0])

            # Amplify for 8-K event-driven filings (per paper)
            if form_type == "8-K":
                roa_shift *= 1.3

            roe_shift = roa_shift * 1.2  # Approximate correlation from paper

            predictions.append(
                {
                    "section": comp.get("section", "unknown"),
                    "predicted_roa_shift": round(roa_shift, 4),
                    "predicted_roe_shift": round(roe_shift, 4),
                    "high_impact": abs(roa_shift) > 0.05,
                }
            )

        avg_roa = np.mean([p["predicted_roa_shift"] for p in predictions])
        high_impact_count = sum(1 for p in predictions if p["high_impact"])

        return {
            "predictions": predictions,
            "avg_roa_shift": round(float(avg_roa), 4),
            "high_impact_count": high_impact_count,
        }

    def cluster_8k_events(
        self,
        events: List[Dict[str, Any]],
        max_days_gap: int = 45,
    ) -> List[Dict[str, Any]]:
        """
        Cluster 8-K filings that are likely related using temporal proximity.

        Groups events within `max_days_gap` days of each other — common pattern
        signaling major corporate actions (e.g., earnings + M&A + exec changes).

        Args:
            events: List of dicts with 'filed_at' (ISO date) and 'text' fields.
            max_days_gap: Maximum days between filings to cluster together.

        Returns:
            List of cluster summaries with event types and risk flags.
        """
        if not events or len(events) < 2:
            return []

        df = pd.DataFrame(events)
        df["filed_at"] = pd.to_datetime(df["filed_at"])
        df = df.sort_values("filed_at").reset_index(drop=True)

        # Extract event type from text
        def get_event_type(text: str) -> str:
            text_lower = str(text).lower()
            if any(
                w in text_lower for w in ["earnings", "results", "financial", "revenue"]
            ):
                return "Earnings"
            if any(
                w in text_lower
                for w in ["merger", "acquisition", "agreement", "transaction"]
            ):
                return "M&A"
            if any(
                w in text_lower
                for w in ["director", "officer", "executive", "resignation"]
            ):
                return "Exec Change"
            if any(w in text_lower for w in ["cybersecurity", "breach", "incident"]):
                return "Cyber"
            return "Other"

        df["event_type"] = df["text"].apply(get_event_type)

        # Temporal DBSCAN clustering
        times = (
            df["filed_at"]
            .values.astype("datetime64[D]")
            .astype(np.int64)
            .reshape(-1, 1)
        )
        clustering = DBSCAN(eps=max_days_gap, min_samples=1, metric="manhattan").fit(
            times
        )
        df["cluster_id"] = clustering.labels_

        clusters = []
        for cluster_id, group in df.groupby("cluster_id"):
            if len(group) < 2:
                continue  # Skip singletons

            cluster_start = group["filed_at"].min()
            cluster_end = group["filed_at"].max()
            types = group["event_type"].unique().tolist()

            clusters.append(
                {
                    "cluster_id": int(cluster_id),
                    "start_date": cluster_start.strftime("%Y-%m-%d"),
                    "end_date": cluster_end.strftime("%Y-%m-%d"),
                    "duration_days": (cluster_end - cluster_start).days,
                    "event_types": types,
                    "filing_count": len(group),
                    "high_risk": "M&A" in types and "Earnings" in types,
                }
            )

        return sorted(clusters, key=lambda x: x["start_date"], reverse=True)


# ═══════════════════════════════════════════════
#  Filing Due Diligence Tool (BaseTool)
# ═══════════════════════════════════════════════


class FilingDueDiligenceTool(BaseTool):
    """
    SEC Filing Due Diligence — NLP change detection, abnormality flagging,
    and financial impact prediction for 10-K and 8-K filings.

    Compares pairs of filing section texts provided in the context and returns
    similarity analysis, sentiment shifts, readability changes, and predicted
    ROA/ROE impacts.
    """

    def __init__(self):
        super().__init__(
            name="filing_due_diligence",
            description=(
                "Analyze SEC filing changes between consecutive 10-K or 8-K filings. "
                "Detects abnormal textual changes (similarity, sentiment, readability), "
                "flags risk factors, predicts financial impact (ROA/ROE shifts), and "
                "clusters related 8-K events. Supports US, India, and EU filings."
            ),
        )
        try:
            self.engine = FilingDueDiligenceEngine()
        except Exception as e:
            logger.warning(f"FilingDueDiligenceEngine init failed: {e}")
            self.engine = None

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Company ticker (e.g., 'MSFT', 'RELIANCE.NS')",
                },
                "filing_pairs": {
                    "type": "array",
                    "description": (
                        "Pairs of filing section texts to compare. Each item: "
                        '{"section": "mda", "prev_text": "...", "curr_text": "...", '
                        '"form_type": "10-K"}'
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "prev_text": {"type": "string"},
                            "curr_text": {"type": "string"},
                            "form_type": {"type": "string", "default": "10-K"},
                        },
                        "required": ["section", "prev_text", "curr_text"],
                    },
                },
                "events_for_clustering": {
                    "type": "array",
                    "description": (
                        "Optional: 8-K events to cluster. Each item: "
                        '{"filed_at": "2025-01-15", "text": "..."}'
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "filed_at": {"type": "string"},
                            "text": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["ticker", "filing_pairs"],
        }

    async def execute(
        self,
        ticker: str,
        filing_pairs: List[Dict[str, str]],
        events_for_clustering: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> ToolResult:
        t0 = time.time()

        if not self.engine:
            return ToolResult(
                success=False,
                data=None,
                error="FilingDueDiligenceEngine not initialized (check scikit-learn install)",
            )

        try:
            region = detect_region(ticker)

            # Step 1: Compare filing pairs
            comparisons = []
            for pair in filing_pairs:
                result = self.engine.compare_filing_texts(
                    prev_text=pair.get("prev_text", ""),
                    curr_text=pair.get("curr_text", ""),
                    section_name=pair.get("section", "mda"),
                    form_type=pair.get("form_type", "10-K"),
                    region=region,
                )
                comparisons.append(result)

            # Step 2: Predict financial impact
            impact = self.engine.predict_financial_impact(
                comparisons,
                form_type=(
                    filing_pairs[0].get("form_type", "10-K") if filing_pairs else "10-K"
                ),
            )

            # Step 3: Cluster 8-K events (if provided)
            clusters = []
            if events_for_clustering:
                clusters = self.engine.cluster_8k_events(events_for_clustering)

            # Build summary
            abnormal_count = sum(1 for c in comparisons if c.get("is_abnormal"))
            avg_similarity = np.mean([c.get("similarity", 0) for c in comparisons])

            elapsed = round((time.time() - t0) * 1000, 1)

            return ToolResult(
                success=True,
                data={
                    "ticker": ticker,
                    "region": region,
                    "summary": {
                        "total_comparisons": len(comparisons),
                        "abnormal_flags": abnormal_count,
                        "avg_similarity": round(float(avg_similarity), 4),
                        "predicted_avg_roa_shift": impact["avg_roa_shift"],
                        "high_impact_count": impact["high_impact_count"],
                        "event_clusters": len(clusters),
                        "high_risk_clusters": sum(
                            1 for c in clusters if c.get("high_risk")
                        ),
                    },
                    "comparisons": comparisons,
                    "financial_impact": impact,
                    "event_clusters": clusters,
                    "thresholds_used": REGION_THRESHOLDS.get(
                        region, REGION_THRESHOLDS["US"]
                    ),
                },
                execution_time_ms=elapsed,
            )

        except Exception as e:
            logger.error(f"Filing due diligence failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                data=None,
                error=f"Filing due diligence analysis failed: {str(e)}",
            )
