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
    description: str = "Researches market opportunities and competitive landscape"
    recommended_model: str = "Gemini 1.5 Flash (Fast Web Search)"

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
        self._current_context = context or {}

        deal_id = context.get("deal_id") if context else None
        industry = context.get("industry", "technology") if context else "technology"

        # Retrieve market-related documents (with deal_id filter)
        market_docs = []
        if deal_id:
            market_docs = await self.retrieve_context(
                f"market industry competition trend growth opportunity for {industry}",
                top_k=8,
                deal_id=deal_id,
            )

        # Build research prompt — LLM will call tools itself via generate_with_tools()
        prompt = self._build_research_prompt(
            task,
            context,
            market_docs,
            {},  # market_data — fetched by LLM via tools
            {},  # competitor_data — fetched by LLM via tools
            {},  # trends_data — fetched by LLM via tools
        )

        # RL Loop: Inject historically successful patterns
        from app.core.quality.agent_quality_store import AgentQualityStore

        quality_store = AgentQualityStore()
        await quality_store.initialize()
        best_practices = await quality_store.get_historical_best_practices(
            self.name, "deal_analysis"
        )

        system_prompt = self._build_system_prompt(best_practices, context)

        # Generate research through gateway with tools (not direct llm.generate)
        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            research_data = self._parse_research_output(response["content"])

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=research_data,
                reasoning=research_data.get("reasoning", ""),
                confidence=self._calculate_confidence(research_data),
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
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

    def _build_system_prompt(
        self, best_practices: List[str] = None, context: Dict = None
    ) -> str:
        """Build system prompt for market research, inheriting stage-aware base prompt"""
        # Start with the base prompt (includes deal stage, thesis, citation discipline)
        base_prompt = self.build_system_prompt(context)

        prompt = (
            base_prompt
            + """

You are an expert market researcher with deep experience in:
- Market sizing and forecasting
- Competitive intelligence
- Industry analysis
- Customer research
- Growth strategy

Additional Market Research Guidelines:
- **CRITICAL: NEVER hallucinate market sizes, competitors, or trends. You must use your provided tools to fetch real data.**
- Use `web_search` to find recent industry reports and competitor news.
- Use `web_scraper` to read competitor websites and press releases.
- Distinguish between TAM, SAM, and SOM based on real retrieved data.
- Analyze both direct and indirect competitors.
- Identify emerging trends and disruptions.
- Be objective about market challenges.
- Cite the explicit tool source (e.g., specific URLs) for every claim provided.
"""
        )
        if best_practices:
            prompt += (
                "\n\nHistorical Best Practices (Learn from past high-scoring deals):\n"
            )
            for bp in best_practices:
                prompt += f"- {bp}\n"

        return prompt

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
        """Analyze a specific competitor using tools (not direct llm.generate)"""
        self._current_context = context
        prompt = f"""Analyze competitor: {competitor_name}

Context:
{json.dumps(context, indent=2)}

Use your tools (web_search, web_scraper) to find real data about this competitor.

Provide:
1. Company overview
2. Product/service offerings
3. Market position
4. Strengths and weaknesses
5. Strategic threats"""

        response = await self.generate_with_tools(
            prompt, self._build_system_prompt(context=context)
        )

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

            # Check if any agent needs to redo their work based on the review
            requires_revision = False
            feedback = synthesis_data.get("reviewer_feedback", [])
            if feedback and len(feedback) > 0:
                requires_revision = True

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data={**synthesis_data, "requires_revision": requires_revision},
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

    def _build_debate_prompt(self, topic: str, agent_outputs: Any) -> str:
        """Build debate synthesis prompt"""
        outputs_list = []
        
        # Handle both list and dict inputs for robustness
        if isinstance(agent_outputs, dict):
            for agent_name, output_data in agent_outputs.items():
                # If output_data is the full AgentOutput dict
                if isinstance(output_data, dict):
                    outputs_list.append({
                        "agent": agent_name,
                        "position": output_data.get("position", "Neutral"),
                        "key_points": output_data.get("key_points", output_data.get("findings", [])),
                        "confidence": output_data.get("confidence", 0.5)
                    })
                else:
                    outputs_list.append({"agent": agent_name, "data": str(output_data)})
        elif isinstance(agent_outputs, list):
            outputs_list = agent_outputs
        
        outputs_str = ""
        for output in outputs_list:
            if isinstance(output, dict):
                outputs_str += f"Agent: {output.get('agent', 'Unknown')}\n"
                outputs_str += f"Position: {output.get('position', 'Neutral')}\n"
                outputs_str += f"Key Points: {json.dumps(output.get('key_points', []))}\n"
                outputs_str += f"Confidence: {output.get('confidence', 0.5)}\n\n"
            else:
                outputs_str += f"Output raw: {str(output)}\n\n"

        return f"""Synthesize the following agent perspectives on: {topic}

Agent Outputs:
{outputs_str}

Provide:
1. Areas of consensus
2. Points of disagreement or logical flaws
3. Key insights from each perspective
4. Synthesized recommendation
5. Peer Review Feedback (If any agent failed to provide adequate analysis, hallucinated data, or made logical errors, list them here so they can be sent back to redo their work).

Respond with structured JSON:
{{
    "consensus_points": [string],
    "disagreements": [{{
        "topic": string,
        "positions": [string]
    }}],
    "key_insights": [string],
    "reviewer_feedback": [{{
        "agent": string,
        "feedback": string,
        "severity": string
    }}],
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
- RIGOROUS PEER REVIEW of analytical work

Guidelines:
- Be objective and fair to all perspectives
- Highlight valid points from each side
- Identify underlying assumptions
- Distinguish between facts and opinions
- STRICTLY EVALUATE if an agent's logic is sound. If an output lacks data, has contradictions, or seems hallucinated, you MUST generate a `reviewer_feedback` item with "high" severity directing the agent to fix it.
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

        # Extract data for scoring using the centralized OutputAdapter
        from app.core.output_adapter import get_output_adapter

        adapter = get_output_adapter()
        adapted = adapter.adapt(
            financial_output=financial_output,
            market_output=market_output,
            risk_output=risk_output,
            legal_output=legal_output,
        )

        team_data = context.get("team_data", {}) if context else {}
        traction_data = context.get("traction_data", {}) if context else {}
        strategic_data = context.get("strategic_data", {}) if context else {}

        # Calculate score
        score_result = scorer.score(
            market_data=adapted["market_data"],
            team_data=team_data,
            traction_data=traction_data,
            financial_data=adapted["financial_data"],
            risk_data=adapted["risk_data"],
            strategic_data=strategic_data,
        )

        # Safety Check: If data coverage is 0 and no agents returned data, fail the scoring
        agent_outputs = context.get("agent_outputs", {}) if context else {}
        if adapted.get("data_coverage", 0) < 0.05 and not any(agent_outputs.values()):
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Scoring aborted: insufficient data across all categories for {context.get('company_name', 'target company')}.",
                confidence=0.0,
            )


        # Attach data coverage internally for output
        data_coverage = adapted.get("data_coverage", 0.0)

        # RL Loop: Store agent quality signals
        from app.core.quality.agent_quality_store import AgentQualityStore

        quality_store = AgentQualityStore()
        await quality_store.initialize()

        # Reward sub-agents based on the final total_score vs target
        # A crude but effective signal: if the deal scores high, the analysis models were strong.
        # In a real system, we'd grade each agent's individual contribution.
        base_reward = 1.0 if score_result.total_score >= 70 else -0.5
        focus_agents = [
            "financial_analyst",
            "legal_advisor",
            "market_researcher",
            "risk_assessor",
        ]
        for ag in focus_agents:
            # We don't have the original action_id here without extensive state tracking,
            # so we log a synthetic completed action + reward immediately
            await quality_store.log_action(
                agent_name=ag,
                task_type="deal_analysis",
                deal_context=(
                    {
                        "industry": context.get("industry", "general"),
                        "type": context.get("type", "general"),
                    }
                    if context
                    else {}
                ),
                action_payload={
                    "final_recommendation_contribution": "See score context"
                },
            )
            # Find the most recently added for this agent and reward it
            import aiosqlite

            async with aiosqlite.connect(quality_store.db_path) as db:
                async with db.execute(
                    "SELECT id FROM agent_actions WHERE agent_name = ? ORDER BY id DESC LIMIT 1",
                    (ag,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await quality_store.reward_action(
                            action_id=row[0],
                            score=base_reward,
                            feedback=f"Final deal score was {score_result.total_score}. Recommendations: {score_result.recommendations}",
                        )

            # Periodically process best practices
            await quality_store.update_best_practices(ag, "deal_analysis")

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "total_score": score_result.total_score,
                "risk_level": score_result.risk_level.value,
                "data_coverage": data_coverage,
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
