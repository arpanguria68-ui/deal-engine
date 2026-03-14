"""Red Team Agent – Strategic Silence Detector for DealForge AI"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import structlog

from app.agents.base import BaseAgent, AgentOutput, IssueTreeNode


class RedTeamAgent(BaseAgent):
    """
    Adversarial Red Team agent that hunts for 'Strategic Silences' —
    branches of the MECE issue tree where critical data is missing
    despite management claims of completeness.

    Also detects historical M&A deal-breakers by querying cross-deal memory.
    """

    name = "red_team"
    description: str = (
        "Adversarial agent that detects strategic silences and hidden deal risks"
    )
    recommended_model: str = "Gemini 1.5 Pro (Adversarial Logic)"

    # Known deal-breaker patterns from historical M&A failures
    DEAL_BREAKER_PATTERNS = [
        "change_of_control",
        "material_adverse_change",
        "earn_out_dispute",
        "environmental_liability",
        "pension_underfunding",
        "off_balance_sheet",
        "related_party_transaction",
        "key_person_dependency",
        "customer_concentration",
        "regulatory_approval_risk",
    ]

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute red team analysis.

        Scans the issue tree for gaps, silent branches, and historical red flags.
        """
        start_time = datetime.now()
        self.logger.info("Red Team sweep initiated", task=task)

        issue_tree = context.get("issue_tree", {}) if context else {}
        agent_outputs = context.get("agent_outputs", {}) if context else {}

        flags: List[Dict[str, Any]] = []

        # 1. Strategic Silence Detection
        silence_flags = self._detect_strategic_silences(issue_tree, agent_outputs)
        flags.extend(silence_flags)

        # 2. Historical Deal-Breaker Scan
        deal_breaker_flags = await self._scan_deal_breakers(context)
        flags.extend(deal_breaker_flags)

        # 3. Data Completeness Check
        completeness_flags = self._check_data_completeness(agent_outputs)
        flags.extend(completeness_flags)

        # 4. Cross-Agent Contradiction Detection
        contradiction_flags = self._detect_contradictions(agent_outputs)
        flags.extend(contradiction_flags)

        # Assign severity levels
        for flag in flags:
            flag["severity"] = self._calculate_severity(flag)

        # Sort by severity (highest first)
        flags.sort(key=lambda f: f["severity"], reverse=True)

        max_severity = max((f["severity"] for f in flags), default=0)
        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "flags": flags,
                "total_flags": len(flags),
                "max_severity": max_severity,
                "recommendation": self._get_recommendation(max_severity),
                "requires_loop_back": max_severity >= 3,
            },
            reasoning=f"Red Team found {len(flags)} flags. Max severity: {max_severity}/5.",
            confidence=0.85,
            execution_time_ms=execution_time,
        )

    def _detect_strategic_silences(
        self, issue_tree: Dict, agent_outputs: Dict
    ) -> List[Dict]:
        """
        Flag branches where the issue tree has 'No Data Found' or where
        agents returned low-confidence or empty results despite the branch
        being marked as important.
        """
        flags = []
        branches = issue_tree.get("sub_branches", [])

        for branch in branches:
            branch_id = branch.get("id", "unknown")
            hypothesis = branch.get("hypothesis", "")
            status = branch.get("status", "open")

            # Check if any agent addressed this branch
            branch_covered = False
            for agent_name, output in agent_outputs.items():
                if isinstance(output, dict):
                    output_text = json.dumps(output).lower()
                    # Check if the branch hypothesis keywords appear in agent output
                    keywords = hypothesis.lower().split()
                    match_count = sum(
                        1 for kw in keywords if kw in output_text and len(kw) > 3
                    )
                    if match_count >= len(keywords) * 0.3:
                        branch_covered = True
                        break

            if not branch_covered and status == "open":
                flags.append(
                    {
                        "type": "strategic_silence",
                        "branch_id": branch_id,
                        "hypothesis": hypothesis,
                        "description": f"Branch '{hypothesis}' has no supporting data from any agent. "
                        f"Management may be omitting critical information.",
                    }
                )

        return flags

    async def _scan_deal_breakers(self, context: Optional[Dict]) -> List[Dict]:
        """
        Query cross-deal memory for historical deal-breaker patterns.
        """
        flags = []
        industry = context.get("industry", "") if context else ""

        # Search memory for precedent failures in same industry
        try:
            precedents = await self.retrieve_context(
                f"deal failure red flag {industry}", top_k=5
            )
            for precedent in precedents:
                content = precedent.get("content", "").lower()
                for pattern in self.DEAL_BREAKER_PATTERNS:
                    if pattern.replace("_", " ") in content:
                        flags.append(
                            {
                                "type": "historical_deal_breaker",
                                "pattern": pattern,
                                "description": f"Historical precedent flagged: {pattern.replace('_', ' ')}. "
                                f"Source: {content[:200]}",
                                "source": "cross_deal_memory",
                            }
                        )
        except Exception as e:
            self.logger.warning("Memory scan failed", error=str(e))

        return flags

    def _check_data_completeness(self, agent_outputs: Dict) -> List[Dict]:
        """
        Check if required data fields are present in agent outputs.
        """
        flags = []

        required_fields = {
            "financial_analyst": ["revenue_analysis", "profitability", "valuation"],
            "legal_advisor": ["legal_risks", "compliance_status"],
            "risk_assessor": ["risk_categories", "risk_matrix"],
            "market_researcher": ["market_size", "competitive_landscape"],
        }

        for agent_name, required in required_fields.items():
            output = agent_outputs.get(agent_name, {})
            if isinstance(output, dict):
                missing = [f for f in required if f not in output]
                if missing:
                    flags.append(
                        {
                            "type": "data_incompleteness",
                            "agent": agent_name,
                            "missing_fields": missing,
                            "description": f"{agent_name} is missing: {', '.join(missing)}",
                        }
                    )

        return flags

    def _detect_contradictions(self, agent_outputs: Dict) -> List[Dict]:
        """
        Detect contradictions between agent outputs.
        E.g., Financial says 'strong growth' but Risk says 'declining market'.
        """
        flags = []

        financial = agent_outputs.get("financial_analyst", {})
        risk = agent_outputs.get("risk_assessor", {})

        # Check for growth vs. risk contradiction
        fin_recommendation = str(financial.get("recommendation", "")).lower()
        risk_level = str(risk.get("overall_risk_level", "")).lower()

        if fin_recommendation == "proceed" and risk_level in ["high", "critical"]:
            flags.append(
                {
                    "type": "cross_agent_contradiction",
                    "agents": ["financial_analyst", "risk_assessor"],
                    "description": "Financial recommends 'proceed' but Risk assessment is "
                    f"'{risk_level}'. These positions must be reconciled.",
                }
            )

        return flags

    def _calculate_severity(self, flag: Dict) -> int:
        """
        Calculate severity (1-5) based on flag type and impact.
        """
        severity_map = {
            "strategic_silence": 4,
            "historical_deal_breaker": 5,
            "data_incompleteness": 2,
            "cross_agent_contradiction": 3,
        }
        return severity_map.get(flag.get("type", ""), 1)

    def _get_recommendation(self, max_severity: int) -> str:
        """Get recommendation based on highest severity flag."""
        if max_severity >= 5:
            return "BLOCK — Critical deal-breaker detected. Escalate to human review."
        elif max_severity >= 4:
            return "ESCALATE — Strategic silence found. Loop back to analysis with targeted queries."
        elif max_severity >= 3:
            return (
                "REVIEW — Contradictions detected. Trigger assumption challenge debate."
            )
        elif max_severity >= 2:
            return "NOTE — Minor data gaps. Proceed with caution."
        return "CLEAR — No significant red flags detected."
