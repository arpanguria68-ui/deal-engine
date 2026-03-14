"""Risk Assessor Agent"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime
from enum import Enum

from app.agents.base import BaseAgent, AgentOutput


class RiskCategory(Enum):
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    LEGAL = "legal"
    MARKET = "market"
    TECHNOLOGY = "technology"
    PEOPLE = "people"


class RiskSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class RiskAssessorAgent(BaseAgent):
    """
    Agent for comprehensive risk assessment

    Responsibilities:
    - Identify and categorize risks
    - Assess probability and impact
    - Recommend mitigation strategies
    - Calculate overall risk score
    """

    name = "risk_assessor"
    description: str = "Identifies and assesses business and transaction risks"
    recommended_model: str = "Gemini 1.5 Pro (Strategic Risk)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute risk assessment task

        Args:
            task: Risk assessment task
            context: Deal context with risk-related data

        Returns:
            AgentOutput with risk assessment
        """
        start_time = datetime.now()
        self.logger.info("Starting risk assessment", task=task)

        deal_id = context.get("deal_id") if context else None

        # Retrieve risk-related documents
        risk_docs = []
        if deal_id:
            risk_docs = await self.retrieve_context(
                f"risk concern issue problem liability exposure {deal_id}", top_k=8
            )

        # Build assessment prompt
        prompt = self._build_assessment_prompt(task, context, risk_docs)
        system_prompt = self._build_system_prompt()

        # Generate assessment
        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            assessment_data = self._parse_assessment_output(response["content"])

            # Calculate overall risk metrics
            risk_metrics = self._calculate_risk_metrics(assessment_data)
            assessment_data["risk_metrics"] = risk_metrics

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=assessment_data,
                reasoning=assessment_data.get("reasoning", ""),
                confidence=self._calculate_confidence(assessment_data),
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Risk assessment failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Assessment failed: {str(e)}",
                confidence=0.0,
            )

    def _build_assessment_prompt(
        self, task: str, context: Optional[Dict], risk_docs: list
    ) -> str:
        """Build risk assessment prompt"""
        context_str = (
            json.dumps(context, indent=2) if context else "No additional context"
        )
        docs_str = (
            "\n".join([f"- {d['content'][:300]}..." for d in risk_docs])
            if risk_docs
            else "No risk documents retrieved"
        )

        return f"""Task: {task}

Context:
{context_str}

Relevant Documents:
{docs_str}

Provide comprehensive risk assessment:
1. Strategic risks (market position, competition)
2. Operational risks (execution, scalability)
3. Financial risks (liquidity, debt, cash flow)
4. Legal/Regulatory risks
5. Technology risks (obsolescence, security)
6. People risks (key person dependency, talent)
7. Market risks (demand, pricing)

For each risk:
- Description
- Category
- Probability (0-1)
- Impact (0-1)
- Severity (critical/high/medium/low)
- Mitigation strategies

Respond with structured JSON:
{{
    "risks": [{{
        "id": string,
        "description": string,
        "category": string,
        "probability": number,
        "impact": number,
        "severity": string,
        "mitigation": [string],
        "owner": string
    }}],
    "risk_summary": {{
        "total_risks": number,
        "critical_count": number,
        "high_count": number,
        "overall_risk_score": number
    }},
    "top_risks": [string],
    "mitigation_priorities": [string],
    "reasoning": string
}}"""

    def _build_system_prompt(self) -> str:
        """Build system prompt for risk assessment"""
        return f"""You are {self.name}, {self.description}.

You are an expert risk analyst with deep experience in:
- Enterprise risk management
- M&A risk assessment
- Due diligence
- Risk mitigation strategy

Guidelines:
- Be thorough but practical
- Distinguish between deal-breakers and manageable risks
- Consider both probability and impact
- Suggest specific, actionable mitigations
- Use quantitative measures where possible
- Consider interdependencies between risks
"""

    def _parse_assessment_output(self, content: str) -> Dict[str, Any]:
        """Parse assessment output"""
        from app.core.json_helpers import extract_and_parse_json

        return extract_and_parse_json(content)

    def _calculate_risk_metrics(self, assessment_data: Dict) -> Dict[str, Any]:
        """Calculate aggregate risk metrics"""
        risks = assessment_data.get("risks", [])

        if not risks:
            return {"overall_score": 0.5, "risk_level": "unknown"}

        # Calculate weighted risk score
        total_risk_score = sum(r["probability"] * r["impact"] for r in risks) / len(
            risks
        )

        # Count by severity
        severity_counts = {
            "critical": sum(1 for r in risks if r.get("severity") == "critical"),
            "high": sum(1 for r in risks if r.get("severity") == "high"),
            "medium": sum(1 for r in risks if r.get("severity") == "medium"),
            "low": sum(1 for r in risks if r.get("severity") == "low"),
        }

        # Determine overall risk level
        if severity_counts["critical"] > 0 or total_risk_score > 0.7:
            risk_level = "critical"
        elif severity_counts["high"] > 2 or total_risk_score > 0.5:
            risk_level = "high"
        elif total_risk_score > 0.3:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "overall_score": round(total_risk_score, 3),
            "risk_level": risk_level,
            "severity_distribution": severity_counts,
            "total_risks_identified": len(risks),
        }

    def _calculate_confidence(self, assessment_data: Dict) -> float:
        """Calculate confidence score"""
        confidence = 0.5

        risks = assessment_data.get("risks", [])
        if len(risks) > 5:
            confidence += 0.2

        if assessment_data.get("risk_metrics", {}).get("overall_score"):
            confidence += 0.15

        if assessment_data.get("mitigation_priorities"):
            confidence += 0.15

        return min(1.0, confidence)

    async def assess_specific_risk(
        self, risk_type: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess a specific type of risk"""
        prompt = f"""Assess {risk_type} risks for:

{json.dumps(context, indent=2)}

Provide detailed assessment with probability, impact, and mitigation strategies."""

        response = await self.llm.generate(prompt, self._build_system_prompt())

        return {"risk_type": risk_type, "assessment": response["content"]}


class MarketRiskAgent(BaseAgent):
    """Specialized agent for market risk assessment"""

    name = "market_risk_agent"
    description = "Specializes in market and competitive risk assessment"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Execute market risk assessment"""
        start_time = datetime.now()

        industry = context.get("industry", "technology") if context else "technology"
        market_data = context.get("market_data", {}) if context else {}

        # Get market data via tool
        market_tool_result = await self.tools.execute(
            "market_data", {"data_type": "market_size", "industry": industry}
        )

        # Build market risk assessment
        market_risks = []

        # Competition risk
        competitors = market_data.get("competitors", [])
        if len(competitors) > 5:
            market_risks.append(
                {
                    "description": f"Intense competition from {len(competitors)} players",
                    "category": "market",
                    "probability": 0.8,
                    "impact": 0.6,
                    "severity": "high",
                    "mitigation": ["Differentiation strategy", "Niche focus"],
                }
            )

        # Market size risk
        tam = market_data.get("tam", 0)
        if tam < 1000000000:  # Less than $1B
            market_risks.append(
                {
                    "description": "Limited market size may constrain growth",
                    "category": "market",
                    "probability": 0.6,
                    "impact": 0.5,
                    "severity": "medium",
                    "mitigation": ["Adjacent market expansion", "Market creation"],
                }
            )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "market_risks": market_risks,
                "market_context": {
                    "industry": industry,
                    "tam": tam,
                    "competitor_count": len(competitors),
                },
            },
            reasoning=f"Market risk assessment for {industry} industry",
            confidence=0.7,
            execution_time_ms=execution_time,
        )
