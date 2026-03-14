"""
Replication evaluator utilities for agent output consistency checks.

Part of the quality & reliability overhaul.  The evaluator offers simple
metrics to determine how much variance occurs when an agent is executed multiple
times with the same input.  The results can be logged to the AgentQualityStore.
"""
from typing import List, Dict
from difflib import SequenceMatcher


def similarity(a: str, b: str) -> float:
    """Return a similarity ratio between two strings (0.0-1.0)."""
    return SequenceMatcher(None, a, b).ratio()


def evaluate_outputs(outputs: List[str]) -> Dict[str, float]:
    """Compute pairwise similarity statistics for a list of outputs.

    Returns a dict with keys:
      - mean_similarity: average of all pairwise ratios
      - min_similarity: lowest pairwise ratio
      - pair_count: number of comparisons made
    """
    sims: List[float] = []
    n = len(outputs)
    for i in range(n):
        for j in range(i + 1, n):
            sims.append(similarity(outputs[i], outputs[j]))
    if not sims:
        return {"mean_similarity": 1.0, "min_similarity": 1.0, "pair_count": 0}
    return {
        "mean_similarity": sum(sims) / len(sims),
        "min_similarity": min(sims),
        "pair_count": len(sims),
    }
