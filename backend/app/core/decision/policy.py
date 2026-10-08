"""
Deal decision policy.

Turns the workflow's evidence into the final recommendation. The score sets
a *base* verdict; guardrails can only *cap* it (never upgrade it), and some
caps also require human review before the deal moves on.

    Score band       → base verdict          (thresholds configurable)
    HaluGate blocked → BLOCKED               + human review
    no score         → capped at HOLD        + human review
    Red Team ≥ 5     → capped at HOLD        + human review   (deal-breaker)
    Red Team ≥ 4     → capped at HOLD        + human review   (strategic silence)
    critical risk    → capped at HOLD        + human review
    low data cover.  → capped at HOLD
    core agent failed→ capped at HOLD        + human review
    other agent fail → capped at CAUTION
    material conflict→ capped at CAUTION
    unverified (HaluGate didn't run) → capped at CAUTION
    require_human_approval config → human review on every verdict

The function is pure, so it can be unit-tested and reused (API, CLI, OFAS).
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Verdict(str, Enum):
    # Ordered from most to least favourable; caps pick the lower of two.
    PROCEED = "PROCEED"
    PROCEED_WITH_CAUTION = "PROCEED WITH CAUTION"
    HOLD = "HOLD"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"


_ORDER = [
    Verdict.PROCEED,
    Verdict.PROCEED_WITH_CAUTION,
    Verdict.HOLD,
    Verdict.REJECT,
    Verdict.BLOCKED,
]

_LABELS = {
    Verdict.PROCEED: "PROCEED - Strong investment opportunity",
    Verdict.PROCEED_WITH_CAUTION: "PROCEED WITH CAUTION - Address identified risks",
    Verdict.HOLD: "HOLD - Requires further due diligence",
    Verdict.REJECT: "REJECT - Does not meet investment criteria",
    Verdict.BLOCKED: "BLOCKED - Escalated to human review",
}

# Scorer / agents use slightly different words for the same level
_RISK_ALIASES = {"medium": "moderate", "severe": "critical", "very_high": "critical"}

# Agents whose absence makes an automated "proceed" unsafe
CORE_AGENTS = ("financial_analyst", "legal_advisor")


@dataclass
class DecisionPolicy:
    proceed_score: float = 75.0
    caution_score: float = 60.0
    hold_score: float = 40.0
    # Risk levels allowed for each favourable verdict
    proceed_risk_levels: tuple = ("low", "moderate")
    caution_risk_levels: tuple = ("low", "moderate", "high")
    red_team_block_severity: int = 4  # ≥ this caps at HOLD + human review
    min_data_coverage: float = 0.3  # below this, cap at HOLD
    require_human_approval: bool = False

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]]) -> "DecisionPolicy":
        config = config or {}
        overrides = dict(config.get("decision_policy") or {})
        if "require_human_approval" in config and "require_human_approval" not in overrides:
            overrides["require_human_approval"] = bool(config["require_human_approval"])
        known = {k: v for k, v in overrides.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Decision:
    verdict: Verdict
    recommendation: str
    score: Optional[float]
    risk_level: Optional[str]
    base_verdict: Optional[Verdict]
    reasons: List[str] = field(default_factory=list)
    caps_applied: List[Dict[str, str]] = field(default_factory=list)
    requires_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        d["base_verdict"] = self.base_verdict.value if self.base_verdict else None
        return d


def _worse(a: Verdict, b: Verdict) -> Verdict:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


def _num(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def decide(state: Dict[str, Any], policy: Optional[DecisionPolicy] = None) -> Decision:
    """Compute the final decision from a DealState-shaped dict."""
    policy = policy or DecisionPolicy()
    scoring = state.get("scoring_output") or {}
    score = _num(state.get("final_score"))
    if score is None:
        score = _num(scoring.get("total_score"))
    risk = str(scoring.get("risk_level") or "").lower() or None
    risk = _RISK_ALIASES.get(risk, risk)

    reasons: List[str] = []
    caps: List[Dict[str, str]] = []
    review = policy.require_human_approval

    # ── Base verdict from the score ──
    base: Optional[Verdict]
    if score is None:
        base = None
        verdict = Verdict.HOLD
        review = True
        reasons.append("No deal score was produced (scoring failed or had no data).")
    else:
        if score >= policy.proceed_score and risk in policy.proceed_risk_levels:
            base = Verdict.PROCEED
        elif score >= policy.caution_score and risk in policy.caution_risk_levels:
            base = Verdict.PROCEED_WITH_CAUTION
        elif score >= policy.hold_score:
            base = Verdict.HOLD
        else:
            base = Verdict.REJECT
        verdict = base
        reasons.append(f"Score {score:.1f}/100 with {risk or 'unknown'} risk → {base.value}.")

    def cap(at: Verdict, gate: str, why: str, needs_review: bool = False) -> None:
        nonlocal verdict, review
        if needs_review:
            review = True
        new = _worse(verdict, at)
        if new != verdict:
            caps.append({"gate": gate, "capped_at": at.value, "reason": why})
            verdict = new
        reasons.append(why)

    # ── Hard gate: HaluGate contradiction ──
    halugate = (state.get("context") or {}).get("halugate_results") or {}
    if halugate.get("blocked"):
        cap(
            Verdict.BLOCKED,
            "halugate",
            "HaluGate found the narrative contradicts the financial data.",
            needs_review=True,
        )
    elif not halugate.get("verified", "blocked" in halugate):
        cap(
            Verdict.PROCEED_WITH_CAUTION,
            "halugate",
            "Narrative was not verified against the financials (HaluGate did not run).",
        )

    # ── Red Team ──
    red = state.get("red_team_output") or {}
    severity = int(_num(red.get("max_severity")) or 0)
    if severity >= policy.red_team_block_severity:
        top = [
            f.get("title") or f.get("description") or f.get("type")
            for f in (red.get("flags") or [])
            if (f.get("severity") or 0) >= policy.red_team_block_severity
        ]
        cap(
            Verdict.HOLD,
            "red_team",
            f"Red Team severity {severity}/5 unresolved"
            + (f": {', '.join(str(t) for t in top[:3] if t)}" if top else "")
            + ".",
            needs_review=True,
        )

    # ── Risk level ──
    if risk == "critical":
        cap(Verdict.HOLD, "risk", "Overall risk is critical.", needs_review=True)

    # ── Data sufficiency ──
    coverage = _num(scoring.get("data_coverage"))
    if coverage is not None and coverage < policy.min_data_coverage:
        cap(
            Verdict.HOLD,
            "data_coverage",
            f"Only {coverage:.0%} of scoring inputs had data (min {policy.min_data_coverage:.0%}).",
        )

    # ── Degraded run: agents that failed ──
    degraded = list(state.get("degraded_agents") or [])
    core_missing = [a for a in degraded if a in CORE_AGENTS]
    if core_missing:
        cap(
            Verdict.HOLD,
            "agent_failure",
            f"Core analysis missing: {', '.join(core_missing)} failed.",
            needs_review=True,
        )
    elif degraded:
        cap(
            Verdict.PROCEED_WITH_CAUTION,
            "agent_failure",
            f"Partial analysis: {', '.join(degraded)} failed.",
        )

    # ── Cross-agent contradictions ──
    material = [
        w for w in (state.get("consistency_warnings") or []) if w.get("severity") == "material"
    ]
    if material:
        cap(
            Verdict.PROCEED_WITH_CAUTION,
            "consistency",
            f"{len(material)} material contradiction(s) between agents.",
        )

    if policy.require_human_approval:
        reasons.append("Policy requires human approval for every decision.")

    return Decision(
        verdict=verdict,
        recommendation=_LABELS[verdict],
        score=score,
        risk_level=risk,
        base_verdict=base,
        reasons=reasons,
        caps_applied=caps,
        requires_human_review=review,
    )
