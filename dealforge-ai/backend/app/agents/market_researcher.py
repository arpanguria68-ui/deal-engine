"""Market Researcher Agent"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class MarketResearcherAgent(BaseAgent):
    """
    Agent for market research and competitive analysis

    Responsibilities:
    - Market sizing (TAM/SAM/SOM)
    - Competitive landscape analysis
    - Industry trend research
    - Customer segment analysis
    - Growth opportunity identification
    """

    name = "market_researcher"
    description = "Researches market opportunities and competitive landscape"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute market research task

        Args:
            task: Research task description
            context: Deal context with market data

        Returns:
            AgentOutput with market research
        """
        start_time = datetime.now()
        self.logger.info("Starting market research", task=task)

        deal_id = context.get("deal_id") if context else None
        industry = context.get("industry", "technology") if context else "technology"

        # Retrieve market-related documents
        market_docs = []
        if deal_id:
            market_docs = await self.retrieve_context(
                f"market industry competition trend growth opportunity {deal_id}",
                top_k=8,
            )

        # Get market data via tools
        market_data_result = await self.tools.execute(
            "market_data", {"data_type": "market_size", "industry": industry}
        )

        competitor_result = await self.tools.execute(
            "market_data", {"data_type": "competitors", "industry": industry}
        )

        trends_result = await self.tools.execute(
            "market_data", {"data_type": "trends", "industry": industry}
        )

        # Build research prompt
        prompt = self._build_research_prompt(
            task,
            context,
            market_docs,
            market_data_result.data if market_data_result.success else {},
            competitor_result.data if competitor_result.success else {},
            trends_result.data if trends_result.success else {},
        )
        system_prompt = self._build_system_prompt()

        # Generate research
        response = await self.llm.generate(prompt, system_prompt)

        try:
            research_data = self._parse_research_output(response["content"])

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=research_data,
                reasoning=research_data.get("reasoning", ""),
                confidence=self._calculate_confidence(research_data),
                execution_time_ms=execution_time,
            )

        except Exception as e:
            self.logger.error("Market research failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Research failed: {str(e)}",
                confidence=0.0,
            )

    def _build_research_prompt(
        self,
        task: str,
        context: Optional[Dict],
        market_docs: list,
        market_data: Dict,
        competitor_data: Dict,
        trends_data: Dict,
    ) -> str:
        """Build market research prompt"""
        context_str = (
            json.dumps(context, indent=2) if context else "No additional context"
        )
        docs_str = (
            "\n".join([f"- {d['content'][:300]}..." for d in market_docs])
            if market_docs
            else "No market documents retrieved"
        )

        return f"""Task: {task}

Context:
{context_str}

Market Data:
{json.dumps(market_data, indent=2)}

Competitor Data:
{json.dumps(competitor_data, indent=2)}

Trends Data:
{json.dumps(trends_data, indent=2)}

Relevant Documents:
{docs_str}

Provide comprehensive market research:
1. Market size and growth (TAM/SAM/SOM)
2. Competitive landscape
3. Industry trends and drivers
4. Customer segments
5. Entry barriers
6. Growth opportunities
7. Market risks

Respond with structured JSON:
{{
    "market_size": {{
        "tam": number,
        "sam": number,
        "som": number,
        "growth_rate": number,
        "currency": string
    }},
    "competitive_landscape": {{
        "market_structure": string,
        "key_players": [{{
            "name": string,
            "market_share": number,
            "strengths": [string],
            "weaknesses": [string]
        }}],
        "competitive_intensity": string
    }},
    "industry_trends": [{{
        "trend": string,
        "impact": string,
        "timeframe": string
    }}],
    "customer_segments": [{{
        "segment": string,
        "size": string,
        "needs": [string],
        "willingness_to_pay": string
    }}],
    "entry_barriers": [string],
    "growth_opportunities": [string],
    "market_risks": [string],
    "investment_thesis": string,
    "reasoning": string
}}"""

    def _build_system_prompt(self) -> str:
        """Build system prompt for market research"""
        return f"""You are {self.name}, {self.description}.

You are an expert market researcher with deep experience in:
- Market sizing and forecasting
- Competitive intelligence
- Industry analysis
- Customer research
- Growth strategy

Guidelines:
- Use specific numbers and cite sources
- Distinguish between TAM, SAM, and SOM
- Analyze both direct and indirect competitors
- Identify emerging trends and disruptions
- Be objective about market challenges
- Consider regional variations
"""

    def _parse_research_output(self, content: str) -> Dict[str, Any]:
        """Parse research output"""
        from app.core.json_helpers import extract_and_parse_json

        return extract_and_parse_json(content)

    def _calculate_confidence(self, research_data: Dict) -> float:
        """Calculate confidence score"""
        confidence = 0.5

        market_size = research_data.get("market_size", {})
        if market_size.get("tam") and market_size.get("sam"):
            confidence += 0.2

        if research_data.get("competitive_landscape", {}).get("key_players"):
            confidence += 0.15

        if research_data.get("industry_trends"):
            confidence += 0.15

        return min(1.0, confidence)

    async def analyze_competitor(
        self, competitor_name: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze a specific competitor"""
        prompt = f"""Analyze competitor: {competitor_name}

Context:
{json.dumps(context, indent=2)}

Provide:
1. Company overview
2. Product/service offerings
3. Market position
4. Strengths and weaknesses
5. Strategic threats"""

        response = await self.llm.generate(prompt, self._build_system_prompt())

        return {"competitor": competitor_name, "analysis": response["content"]}


class DebateModeratorAgent(BaseAgent):
    """
    Agent for moderating multi-agent debates

    Responsibilities:
    - Facilitate agent discussions
    - Synthesize conflicting viewpoints
    - Identify consensus and disagreements
    - Guide toward resolution
    """

    name = "debate_moderator"
    description = "Moderates multi-agent debates and synthesizes viewpoints"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute debate moderation

        Args:
            task: Moderation task
            context: Contains agent outputs to synthesize

        Returns:
            AgentOutput with synthesized debate results
        """
        start_time = datetime.now()

        agent_outputs = context.get("agent_outputs", []) if context else []
        debate_topic = (
            context.get("topic", "Deal evaluation") if context else "Deal evaluation"
        )

        if not agent_outputs:
            return AgentOutput(
                success=False,
                data={},
                reasoning="No agent outputs to synthesize",
                confidence=0.0,
            )

        # Build debate synthesis prompt
        prompt = self._build_debate_prompt(debate_topic, agent_outputs)
        system_prompt = self._build_system_prompt()

        response = await self.llm.generate(prompt, system_prompt)

        try:
            synthesis_data = self._parse_synthesis_output(response["content"])

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=synthesis_data,
                reasoning=synthesis_data.get("reasoning", ""),
                confidence=0.75,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            self.logger.error("Debate synthesis failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Synthesis failed: {str(e)}",
                confidence=0.0,
            )

    def _build_debate_prompt(self, topic: str, agent_outputs: List[Dict]) -> str:
        """Build debate synthesis prompt"""
        outputs_str = "\n\n".join(
            [
                f"Agent: {output.get('agent', 'Unknown')}\n"
                f"Position: {output.get('position', 'Neutral')}\n"
                f"Key Points: {json.dumps(output.get('key_points', []))}\n"
                f"Confidence: {output.get('confidence', 0.5)}"
                for output in agent_outputs
            ]
        )

        return f"""Synthesize the following agent perspectives on: {topic}

Agent Outputs:
{outputs_str}

Provide:
1. Areas of consensus
2. Points of disagreement
3. Key insights from each perspective
4. Synthesized recommendation
5. Confidence level in synthesis

Respond with structured JSON:
{{
    "consensus_points": [string],
    "disagreements": [{{
        "topic": string,
        "positions": [string]
    }}],
    "key_insights": [string],
    "synthesized_recommendation": string,
    "confidence": number,
    "next_steps": [string],
    "reasoning": string
}}"""

    def _build_system_prompt(self) -> str:
        """Build system prompt for debate moderation"""
        return f"""You are {self.name}, {self.description}.

You are an expert facilitator with skills in:
- Synthesizing multiple viewpoints
- Identifying common ground
- Resolving conflicts
- Building consensus

Guidelines:
- Be objective and fair to all perspectives
- Highlight valid points from each side
- Identify underlying assumptions
- Distinguish between facts and opinions
- Provide clear, actionable synthesis
"""

    def _parse_synthesis_output(self, content: str) -> Dict[str, Any]:
        """Parse synthesis output"""
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()

        return json.loads(json_str)


class ScoringAgent(BaseAgent):
    """
    Agent for final deal scoring

    Responsibilities:
    - Aggregate agent outputs
    - Calculate final deal score
    - Generate investment recommendation
    """

    name = "scoring_agent"
    description = "Calculates final deal scores and investment recommendations"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Execute deal scoring"""
        start_time = datetime.now()

        # Get inputs from other agents
        financial_output = context.get("financial_output", {}) if context else {}
        legal_output = context.get("legal_output", {}) if context else {}
        risk_output = context.get("risk_output", {}) if context else {}
        market_output = context.get("market_output", {}) if context else {}

        # Use DealScorer for calculation
        from app.core.scoring.deal_scorer import DealScorer

        scorer = DealScorer()

        # Extract data for scoring
        market_data = market_output.get("market_size", {})
        market_data["competition_level"] = market_output.get(
            "competitive_landscape", {}
        ).get("competitive_intensity", "medium")

        team_data = context.get("team_data", {}) if context else {}

        traction_data = context.get("traction_data", {}) if context else {}

        financial_data = financial_output.get("revenue_analysis", {})
        financial_data.update(financial_output.get("profitability", {}))
        financial_data.update(financial_output.get("cash_flow", {}))

        risk_data = {
            "legal_risks": legal_output.get("key_legal_risks", []),
            "regulatory_risks": legal_output.get("regulatory_compliance", {}).get(
                "gaps", []
            ),
            "market_risks": market_output.get("market_risks", []),
        }

        strategic_data = context.get("strategic_data", {}) if context else {}

        # Calculate score
        score_result = scorer.score(
            market_data=market_data,
            team_data=team_data,
            traction_data=traction_data,
            financial_data=financial_data,
            risk_data=risk_data,
            strategic_data=strategic_data,
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "total_score": score_result.total_score,
                "risk_level": score_result.risk_level.value,
                "components": [
                    {
                        "name": c.name,
                        "score": round(c.score * 100, 2),
                        "weight": c.weight,
                        "factors": c.factors,
                    }
                    for c in score_result.components
                ],
                "recommendations": score_result.recommendations,
                "red_flags": score_result.red_flags,
                "green_flags": score_result.green_flags,
                "confidence": score_result.confidence,
            },
            reasoning=f"Deal scored at {score_result.total_score}/100 with {score_result.risk_level.value} risk",
            confidence=score_result.confidence,
            execution_time_ms=execution_time,
        )
