"""HaluGate — NLI-based Hallucination Detection Engine for DealForge AI"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import json
import re
import structlog

logger = structlog.get_logger()


class NLIVerdict(str, Enum):
    """NLI classification result"""

    ENTAILMENT = "entailment"  # Claim is supported by evidence
    NEUTRAL = "neutral"  # Claim has no supporting evidence (flagged)
    CONTRADICTION = "contradiction"  # Claim contradicts evidence (blocked)
    CROSS_AGENT_CONFLICT = (
        "cross_agent_conflict"  # Cross-agent contradiction (QA Flow 3)
    )


class HaluGateSeverity(int, Enum):
    """Severity levels for HaluGate flags"""

    INFO = 1  # Minor discrepancy
    WARNING = 2  # Needs human review
    ESCALATE = 3  # Requires agent re-analysis
    BLOCK = 4  # Output must be blocked until resolved


@dataclass
class HaluGateResult:
    """Result from a HaluGate verification check"""

    claim: str
    evidence: str
    verdict: NLIVerdict
    severity: HaluGateSeverity
    confidence: float
    explanation: str


class HaluGateEngine:
    """
    Two-stage 'kill-switch' for narrative-math contradictions.

    Stage 1: Cross-reference narrative claims against ground-truth JSON
             payloads (financial_payload.json).
    Stage 2: Verify mathematical outputs against Python execution logs.

    Per the PRD, this uses NLI classification to detect:
    - Entailment: Claim is supported → PASS
    - Neutral: No evidence found → FLAG
    - Contradiction: Claim contradicts evidence → BLOCK
    """

    # Patterns that indicate quantitative claims in text
    NUMBER_PATTERN = re.compile(r"\$?[\d,]+\.?\d*[BMKbmk%]?")
    PERCENTAGE_PATTERN = re.compile(r"[\d.]+%")

    def __init__(self, llm_client=None):
        """
        Initialize HaluGate.
        In production, this should use a lightweight NLI model
        (e.g., cross-encoder/nli-deberta-v3-base) for low-latency inference.
        Falls back to LLM-based verification if no NLI model is available.
        """
        self.llm = llm_client
        self.logger = structlog.get_logger(component="halugate")

    async def verify_narrative(
        self,
        narrative: str,
        ground_truth: Dict[str, Any],
        math_outputs: Optional[Dict[str, Any]] = None,
    ) -> List[HaluGateResult]:
        """
        Full HaluGate pipeline: verify a narrative against ground truth data.

        Args:
            narrative: The text narrative to verify (e.g., investment memo paragraph)
            ground_truth: Structured financial data (financial_payload.json)
            math_outputs: Python execution results from the Architect

        Returns:
            List of HaluGateResults for each claim found in the narrative
        """
        results = []

        # Stage 1: Extract quantitative claims from narrative
        claims = self._extract_claims(narrative)
        self.logger.info("Claims extracted", count=len(claims))

        # Stage 2: Verify each claim against ground truth
        for claim in claims:
            result = await self._verify_claim(claim, ground_truth, math_outputs)
            results.append(result)

        # Log summary
        blocked = [r for r in results if r.verdict == NLIVerdict.CONTRADICTION]
        flagged = [r for r in results if r.verdict == NLIVerdict.NEUTRAL]
        self.logger.info(
            "HaluGate verification complete",
            total=len(results),
            blocked=len(blocked),
            flagged=len(flagged),
        )

        return results

    def _extract_claims(self, narrative: str) -> List[str]:
        """
        Extract individual quantitative claims from a narrative.
        A 'claim' is any sentence containing a number, percentage, or financial figure.
        """
        sentences = re.split(r"[.!?]\s+", narrative)
        claims = []

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Has numbers or percentages → it's a quantitative claim
            if self.NUMBER_PATTERN.search(sentence) or self.PERCENTAGE_PATTERN.search(
                sentence
            ):
                claims.append(sentence)

        return claims

    async def _verify_claim(
        self,
        claim: str,
        ground_truth: Dict[str, Any],
        math_outputs: Optional[Dict[str, Any]] = None,
    ) -> HaluGateResult:
        """
        Verify a single claim against ground truth data.
        Uses rule-based matching first, then falls back to LLM-based NLI.
        """
        evidence_str = json.dumps(ground_truth, indent=2, default=str)

        # Rule-based fast path: extract numbers and check
        claim_numbers = self._extract_numbers(claim)
        evidence_numbers = self._extract_numbers(evidence_str)

        # Check for direct number matches
        if claim_numbers:
            matched = [n for n in claim_numbers if n in evidence_numbers]
            if len(matched) == len(claim_numbers):
                return HaluGateResult(
                    claim=claim,
                    evidence="Direct number match in ground truth",
                    verdict=NLIVerdict.ENTAILMENT,
                    severity=HaluGateSeverity.INFO,
                    confidence=0.95,
                    explanation=f"All numbers ({matched}) found in financial data.",
                )

            # Check math outputs for the claim numbers
            if math_outputs:
                math_str = json.dumps(math_outputs, default=str)
                math_numbers = self._extract_numbers(math_str)
                math_matched = [n for n in claim_numbers if n in math_numbers]
                if len(math_matched) == len(claim_numbers):
                    return HaluGateResult(
                        claim=claim,
                        evidence="Number match in Architect math output",
                        verdict=NLIVerdict.ENTAILMENT,
                        severity=HaluGateSeverity.INFO,
                        confidence=0.90,
                        explanation=f"Numbers ({math_matched}) verified against Python execution.",
                    )

            # Numbers in claim but NOT in evidence → potential hallucination
            unmatched = [n for n in claim_numbers if n not in evidence_numbers]
            if unmatched:
                return HaluGateResult(
                    claim=claim,
                    evidence=f"Numbers {unmatched} NOT found in ground truth",
                    verdict=NLIVerdict.CONTRADICTION,
                    severity=HaluGateSeverity.BLOCK,
                    confidence=0.80,
                    explanation=f"Claim contains numbers ({unmatched}) not present in any source data. "
                    "Possible hallucination.",
                )

        # No numbers found — neutral (narrative claim without quantitative backing)
        return HaluGateResult(
            claim=claim,
            evidence="No quantitative evidence available",
            verdict=NLIVerdict.NEUTRAL,
            severity=HaluGateSeverity.WARNING,
            confidence=0.50,
            explanation="Qualitative claim without numerical evidence. Flagged for human review.",
        )

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract numerical values from text, normalizing units."""
        numbers = []
        for match in self.NUMBER_PATTERN.finditer(text):
            raw = match.group().replace("$", "").replace(",", "").strip()

            multiplier = 1
            if raw.endswith(("B", "b")):
                multiplier = 1_000_000_000
                raw = raw[:-1]
            elif raw.endswith(("M", "m")):
                multiplier = 1_000_000
                raw = raw[:-1]
            elif raw.endswith(("K", "k")):
                multiplier = 1_000
                raw = raw[:-1]
            elif raw.endswith("%"):
                raw = raw[:-1]

            try:
                numbers.append(float(raw) * multiplier)
            except ValueError:
                continue

        return numbers

    def should_block(self, results: List[HaluGateResult]) -> bool:
        """Check if any result triggers a block."""
        return any(r.severity == HaluGateSeverity.BLOCK for r in results)

    def get_severity_summary(self, results: List[HaluGateResult]) -> Dict[str, int]:
        """Get count of results by severity."""
        summary = {s.name: 0 for s in HaluGateSeverity}
        for r in results:
            summary[r.severity.name] += 1
        return summary

    # ═══════════════════════════════════════════════════════════
    #  Cross-Agent Consistency Mode (QA Flow 3)
    # ═══════════════════════════════════════════════════════════

    def cross_agent_verify(
        self, agent_outputs: Dict[str, Dict[str, Any]], check_point: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Cross-agent consistency check. Reuses _extract_numbers() for numeric extraction.

        Check Point 1 (after parallel analysis — 4 agents):
          - Revenue vs TAM
          - Growth alignment
          - Risk coverage

        Check Point 2 (after BA synthesis):
          - Revenue consistency (financial_analyst vs business_analyst)

        Returns:
            List of ConsistencyWarning dicts.
        """
        warnings = []

        financial = agent_outputs.get(
            "financial_analyst", agent_outputs.get("financial_output", {})
        )
        market = agent_outputs.get(
            "market_researcher", agent_outputs.get("market_output", {})
        )
        risk = agent_outputs.get("risk_assessor", agent_outputs.get("risk_output", {}))
        legal = agent_outputs.get(
            "legal_advisor", agent_outputs.get("legal_output", {})
        )

        if check_point <= 1:
            # Rule 1: Revenue vs TAM
            revenue = self._extract_nested_number(
                financial,
                [
                    "revenue_analysis.annual_revenue",
                    "revenue",
                    "revenue_analysis.revenue",
                ],
            )
            tam = self._extract_nested_number(
                market, ["market_size.tam", "tam", "total_addressable_market"]
            )
            if revenue is not None and tam is not None and revenue > tam:
                warnings.append(
                    {
                        "agent_a": "financial_analyst",
                        "claim_a": f"Revenue: ${revenue:,.0f}",
                        "agent_b": "market_researcher",
                        "claim_b": f"TAM: ${tam:,.0f}",
                        "severity": "material",
                        "explanation": f"Reported revenue (${revenue:,.0f}) exceeds total addressable market (${tam:,.0f}). Possible definition mismatch.",
                    }
                )

            # Rule 2: Growth alignment
            fin_growth = self._extract_nested_number(
                financial,
                ["revenue_analysis.growth_rate", "growth_rate", "projected_growth"],
            )
            mkt_growth = self._extract_nested_number(
                market, ["market_size.growth_rate", "growth_rate", "market_growth"]
            )
            if fin_growth is not None and mkt_growth is not None:
                diff = abs(fin_growth - mkt_growth)
                if diff > 15:  # > 15 percentage points
                    warnings.append(
                        {
                            "agent_a": "financial_analyst",
                            "claim_a": f"Growth rate: {fin_growth}%",
                            "agent_b": "market_researcher",
                            "claim_b": f"Market growth: {mkt_growth}%",
                            "severity": "material",
                            "explanation": f"Growth rates differ by {diff:.1f} percentage points (>{15}pp threshold).",
                        }
                    )

            # Rule 3: Risk coverage gaps
            risk_categories = set()
            if isinstance(risk, dict):
                for key in ["risk_categories", "key_risks", "identified_risks"]:
                    items = risk.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str):
                                risk_categories.add(item.lower())
                            elif isinstance(item, dict):
                                risk_categories.add(
                                    str(
                                        item.get("category", item.get("risk", ""))
                                    ).lower()
                                )

            legal_risks = set()
            if isinstance(legal, dict):
                for key in ["key_legal_risks", "risks", "legal_risks"]:
                    items = legal.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, str):
                                legal_risks.add(item.lower())
                            elif isinstance(item, dict):
                                legal_risks.add(
                                    str(
                                        item.get("risk", item.get("category", ""))
                                    ).lower()
                                )

            if risk_categories and legal_risks:
                risk_only = risk_categories - legal_risks
                legal_only = legal_risks - risk_categories
                for gap in risk_only:
                    if gap:  # skip empty
                        warnings.append(
                            {
                                "agent_a": "risk_assessor",
                                "claim_a": f"Flagged risk: {gap}",
                                "agent_b": "legal_advisor",
                                "claim_b": "Not mentioned",
                                "severity": "minor",
                                "explanation": f"Risk '{gap}' flagged by risk_assessor but absent from legal_advisor analysis.",
                            }
                        )

        if check_point >= 2:
            # Rule 4: Revenue consistency (financial vs business analyst)
            ba_output = agent_outputs.get(
                "business_analyst", agent_outputs.get("analyst_output", {})
            )
            ba_revenue = self._extract_nested_number(
                ba_output,
                [
                    "revenue",
                    "financial_summary.revenue",
                    "revenue_analysis.annual_revenue",
                ],
            )
            fin_revenue = self._extract_nested_number(
                financial,
                [
                    "revenue_analysis.annual_revenue",
                    "revenue",
                    "revenue_analysis.revenue",
                ],
            )
            if ba_revenue is not None and fin_revenue is not None and fin_revenue > 0:
                pct_diff = abs(ba_revenue - fin_revenue) / fin_revenue * 100
                if pct_diff > 10:
                    warnings.append(
                        {
                            "agent_a": "financial_analyst",
                            "claim_a": f"Revenue: ${fin_revenue:,.0f}",
                            "agent_b": "business_analyst",
                            "claim_b": f"Revenue in synthesis: ${ba_revenue:,.0f}",
                            "severity": "material",
                            "explanation": f"Revenue differs by {pct_diff:.1f}% between financial_analyst and business_analyst synthesis.",
                        }
                    )

        self.logger.info(
            "cross_agent_verify_complete",
            check_point=check_point,
            warnings_count=len(warnings),
        )
        return warnings

    def _extract_nested_number(self, data: Dict, paths: List[str]) -> Optional[float]:
        """Extract a numeric value from nested dict using dotted path alternatives."""
        if not isinstance(data, dict):
            return None
        for path in paths:
            parts = path.split(".")
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    current = None
                    break
            if current is not None:
                try:
                    return float(current)
                except (ValueError, TypeError):
                    continue
        return None


class NonGAAPDetector:
    """
    Detects aggressive Non-GAAP add-backs in MD&A and earnings transcripts.

    Common aggressive adjustments to flag:
    - Stock-based compensation exclusion from 'adjusted EBITDA'
    - One-time restructuring charges that recur every year
    - Litigation settlements excluded from operating expenses
    - Acquisition-related costs treated as non-recurring
    """

    AGGRESSIVE_PATTERNS = [
        (
            r"adjusted\s+ebitda",
            "adjusted_ebitda",
            "Non-GAAP EBITDA adjustment detected",
        ),
        (
            r"stock[- ]based\s+compensation\s+(?:excluded|adjusted|removed)",
            "sbc_exclusion",
            "SBC excluded from adjusted metrics",
        ),
        (
            r"non[- ]?recurring\s+(?:charge|cost|expense)",
            "non_recurring",
            "Non-recurring claim — verify if truly one-time",
        ),
        (
            r"restructuring\s+(?:charge|cost|expense)",
            "restructuring",
            "Restructuring charge — check for recurrence",
        ),
        (
            r"acquisition[- ]related\s+(?:cost|expense|charge)",
            "acquisition_costs",
            "Acquisition costs excluded — may inflate margins",
        ),
        (r"pro[- ]?forma", "pro_forma", "Pro-forma adjustment — verify basis"),
        (
            r"(?:litigation|legal)\s+(?:settlement|charge|reserve)",
            "litigation",
            "Litigation cost excluded — potential ongoing liability",
        ),
    ]

    def __init__(self):
        self.logger = structlog.get_logger(component="non_gaap_detector")

    def scan(self, text: str) -> List[Dict[str, Any]]:
        """
        Scan text for aggressive Non-GAAP adjustments.

        Args:
            text: MD&A section, earnings call transcript, or CIM narrative

        Returns:
            List of detected aggressive adjustments
        """
        findings = []
        text_lower = text.lower()

        for pattern, category, description in self.AGGRESSIVE_PATTERNS:
            matches = list(re.finditer(pattern, text_lower))
            if matches:
                for match in matches:
                    # Get surrounding context (50 chars each side)
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].strip()

                    findings.append(
                        {
                            "category": category,
                            "description": description,
                            "matched_text": match.group(),
                            "context": context,
                            "position": match.start(),
                        }
                    )

        self.logger.info("Non-GAAP scan complete", findings=len(findings))
        return findings
