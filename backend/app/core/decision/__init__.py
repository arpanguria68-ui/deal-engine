"""Deal decision layer: turns workflow evidence into a guarded recommendation."""

from app.core.decision.policy import Decision, DecisionPolicy, Verdict, decide

__all__ = ["Decision", "DecisionPolicy", "Verdict", "decide"]
