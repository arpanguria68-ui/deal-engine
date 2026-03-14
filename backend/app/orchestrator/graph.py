from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import asyncio
import structlog

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.orchestrator.state import (
    DealState,
    DealStage,
    AgentState,
    WorkflowConfig,
    create_initial_state,
    update_state,
    add_stage_to_history,
    set_agent_state,
    all_agents_completed,
    has_errors,
    get_error_agents,
)

from app.agents.base import get_agent_registry
from app.agents.financial_analyst import FinancialAnalystAgent, ValuationAgent
from app.agents.legal_advisor import LegalAdvisorAgent, ComplianceAgent
from app.agents.risk_assessor import RiskAssessorAgent, MarketRiskAgent
from app.agents.market_researcher import (
    MarketResearcherAgent,
    DebateModeratorAgent,
    ScoringAgent,
)
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.red_team_agent import RedTeamAgent
from app.agents.due_diligence_agent import CommercialDueDiligenceAgent
from app.agents.investment_memo_agent import InvestmentMemoAgent
from app.agents.treasury_agent import TreasuryCashAgent
from app.agents.dcf_lbo_architect import DCFLBOArchitectAgent
from app.agents.project_manager import ProjectManagerAgent
from app.agents.compiler_agent import ReportCompilerAgent
from app.agents.data_curator_agent import DataCuratorAgent
from app.agents.complex_reasoning_agent import ComplexReasoningAgent
from app.agents.report_architect_agent import ReportArchitectAgent
from app.agents.advanced_financial_modeler import AdvancedFinancialModelerAgent
from app.core.halugate import HaluGateEngine, HaluGateSeverity

logger = structlog.get_logger()


class DealOrchestrator:
    """Orchestrates multi-agent deal workflows using LangGraph"""

    def __init__(self, config: Optional[WorkflowConfig] = None):
        self.logger = structlog.get_logger()
        self.config = config or self._default_config()
        self.agent_registry = get_agent_registry()
        self._register_agents()
        # Concurrency limiter: prevents API quota exhaustion
        max_concurrent = self.config.get("max_concurrent_agents", 4)
        self._agent_semaphore = asyncio.Semaphore(max_concurrent)
        self.graph = self._build_graph()

    def _default_config(self) -> WorkflowConfig:
        """Default workflow configuration"""
        return {
            "max_iterations": 10,
            "timeout_seconds": 300,
            "parallel_execution": True,
            "max_concurrent_agents": 4,
            "enabled_agents": [
                "financial_analyst",
                "legal_advisor",
                "risk_assessor",
                "market_researcher",
            ],
            "agent_timeout_seconds": 60,
            "enable_reflection": True,
            "reflection_threshold": 0.6,
            "require_human_approval": False,
            "approval_stages": [],
            "scoring_weights": {},
            "min_deal_score": 0.5,
        }

    def _register_agents(self):
        """Register all available agents"""
        # Financial agents
        self.agent_registry.register(FinancialAnalystAgent())
        self.agent_registry.register(ValuationAgent())
        self.agent_registry.register(DCFLBOArchitectAgent())

        # Legal agents
        self.agent_registry.register(LegalAdvisorAgent())
        self.agent_registry.register(ComplianceAgent())

        # Risk agents
        self.agent_registry.register(RiskAssessorAgent())
        self.agent_registry.register(MarketRiskAgent())

        # Market and synthesis agents
        self.agent_registry.register(MarketResearcherAgent())
        self.agent_registry.register(DebateModeratorAgent())
        self.agent_registry.register(ScoringAgent())

        # Red Team agent
        self.agent_registry.register(RedTeamAgent())

        # Output Formatting agent
        self.agent_registry.register(BusinessAnalystAgent())

        # Deal lifecycle agents (used by chat pipeline)
        self.agent_registry.register(CommercialDueDiligenceAgent())
        self.agent_registry.register(InvestmentMemoAgent())
        self.agent_registry.register(TreasuryCashAgent())
        self.agent_registry.register(ProjectManagerAgent())
        self.agent_registry.register(ReportCompilerAgent())
        self.agent_registry.register(DataCuratorAgent())
        self.agent_registry.register(ComplexReasoningAgent())
        self.agent_registry.register(ReportArchitectAgent())
        self.agent_registry.register(AdvancedFinancialModelerAgent())

        # HaluGate engine (not an agent, but a verification layer)
        self.halugate = HaluGateEngine()

        self.logger.info(
            "All agents registered (including Red Team + HaluGate + Deal Lifecycle)"
        )

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        # Define the state graph
        workflow = StateGraph(DealState)

        # Add nodes
        workflow.add_node("init", self._node_init)
        workflow.add_node("screening", self._node_screening)
        workflow.add_node("parallel_analysis", self._node_parallel_analysis)
        workflow.add_node("consistency_check", self._node_consistency_check)
        workflow.add_node("advanced_financial", self._node_advanced_financial)
        workflow.add_node("data_curator", self._node_data_curator)
        workflow.add_node("complex_reasoning", self._node_complex_reasoning)
        workflow.add_node("report_architect", self._node_report_architect)
        workflow.add_node("debate", self._node_debate)
        workflow.add_node("red_team", self._node_red_team)
        workflow.add_node("scoring", self._node_scoring)
        workflow.add_node("halugate_verify", self._node_halugate_verify)
        workflow.add_node("report_formatting", self._node_report_formatting)
        workflow.add_node("compiler", self._node_compiler)
        workflow.add_node("decision", self._node_decision)
        workflow.add_node("error_handler", self._node_error_handler)
        workflow.add_node("complete", self._node_complete)

        # Define edges
        workflow.set_entry_point("init")

        # From init
        workflow.add_conditional_edges(
            "init",
            self._should_continue_to_screening,
            {"screening": "screening", "error": "error_handler"},
        )

        # From screening
        workflow.add_conditional_edges(
            "screening",
            self._should_continue_to_analysis,
            {
                "analysis": "parallel_analysis",
                "error": "error_handler",
                "reject": "complete",
            },
        )

        # From parallel analysis → consistency_check
        workflow.add_conditional_edges(
            "parallel_analysis",
            self._should_continue_to_advanced_financial,
            {
                "advanced_financial": "consistency_check",
                "error": "error_handler",
                "wait": "parallel_analysis",
            },
        )

        # From consistency_check → advanced_financial
        workflow.add_edge("consistency_check", "advanced_financial")

        workflow.add_conditional_edges(
            "advanced_financial",
            self._should_continue_to_data_curator,
            {"data_curator": "data_curator", "error": "error_handler"},
        )

        workflow.add_conditional_edges(
            "data_curator",
            self._should_continue_to_complex_reasoning,
            {"complex_reasoning": "complex_reasoning", "error": "error_handler"},
        )

        workflow.add_conditional_edges(
            "complex_reasoning",
            self._should_continue_to_debate,
            {"debate": "debate", "error": "error_handler"},
        )

        # From debate (Peer Review) → Red Team OR loop back for revisions
        workflow.add_conditional_edges(
            "debate",
            self._should_continue_after_debate,
            {
                "red_team": "red_team",
                "loop_back": "parallel_analysis",
                "error": "error_handler",
            },
        )

        # From Red Team → scoring OR loop back to analysis
        workflow.add_conditional_edges(
            "red_team",
            self._should_continue_after_red_team,
            {
                "scoring": "scoring",
                "loop_back": "parallel_analysis",
                "error": "error_handler",
            },
        )

        # From scoring → HaluGate verification
        workflow.add_conditional_edges(
            "scoring",
            self._should_continue_to_halugate,
            {"halugate": "halugate_verify", "error": "error_handler"},
        )

        # From HaluGate → report_architect OR escalate
        workflow.add_conditional_edges(
            "halugate_verify",
            self._should_continue_after_halugate,
            {
                "report_architect": "report_architect",
                "escalate": "complete",
                "error": "error_handler",
            },
        )

        # From report_architect -> report_formatting
        workflow.add_conditional_edges(
            "report_architect",
            self._should_continue_to_report_formatting,
            {"report_formatting": "report_formatting", "error": "error_handler"},
        )

        # From report_formatting -> compiler
        workflow.add_conditional_edges(
            "report_formatting",
            self._should_continue_to_compiler,
            {"compiler": "compiler", "error": "error_handler"},
        )

        # From compiler -> decision
        workflow.add_conditional_edges(
            "compiler",
            self._should_continue_to_decision,
            {"decision": "decision", "error": "error_handler"},
        )

        # From decision
        workflow.add_conditional_edges(
            "decision",
            self._should_complete,
            {"complete": "complete", "error": "error_handler"},
        )

        # Error handler can go to complete or retry
        workflow.add_conditional_edges(
            "error_handler",
            self._handle_error_decision,
            {"complete": "complete", "retry": "screening"},
        )

        # Complete is terminal
        workflow.add_edge("complete", END)

        # Compile with checkpointing
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)

    # ===== Node Functions =====

    async def _node_init(self, state: DealState) -> DealState:
        """Initialize the workflow"""
        self.logger.info("Initializing workflow", deal_id=state["deal_id"])

        return update_state(
            state,
            {
                "current_stage": DealStage.INIT,
                "started_at": datetime.utcnow().isoformat(),
            },
        )

    async def _node_screening(self, state: DealState) -> DealState:
        """Initial screening phase"""
        self.logger.info("Running screening", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.SCREENING})
        state = add_stage_to_history(state, DealStage.SCREENING)

        # Basic validation - check if we have minimum required info
        context = state.get("context", {})

        if not context.get("target_company"):
            return update_state(
                state,
                {
                    "error_message": "Missing target company information",
                    "final_recommendation": "REJECT - Insufficient information",
                },
            )

        # Quick market check
        market_agent = self.agent_registry.get("market_researcher")
        if market_agent:
            try:
                result = await market_agent.run(
                    f"Quick market assessment for {context.get('target_company')}",
                    context={"deal_id": state["deal_id"], **context},
                )

                if result.success:
                    state = update_state(state, {"market_output": result.data})

                    # Check for immediate red flags
                    market_size = result.data.get("market_size", {}).get("tam", 0)
                    if market_size < 100000000:  # Less than $100M TAM
                        self.logger.warning(
                            "Small market size detected", tam=market_size
                        )

            except Exception as e:
                self.logger.error("Screening failed", error=str(e))

        return state

    async def _node_parallel_analysis(self, state: DealState) -> DealState:
        """Run agents in parallel for analysis"""
        self.logger.info("Running parallel analysis", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.DUE_DILIGENCE})
        state = add_stage_to_history(state, DealStage.DUE_DILIGENCE)

        context = state.get("context", {})
        context["deal_id"] = state["deal_id"]

        # Define agents to run
        agents_to_run = [
            ("financial_analyst", "financial_output"),
            ("legal_advisor", "legal_output"),
            ("risk_assessor", "risk_output"),
            ("market_researcher", "market_output"),
        ]

        # Extract peer review feedback if we are looping back
        debate_output = state.get("debate_output", {})
        peer_feedback = (
            debate_output.get("reviewer_feedback", []) if debate_output else []
        )

        if self.config.get("parallel_execution", True):
            # Run agents in parallel
            tasks = []
            for agent_name, output_key in agents_to_run:
                agent = self.agent_registry.get(agent_name)
                if agent:
                    # Inject specific feedback for this agent
                    agent_specific_context = context.copy()
                    for f in peer_feedback:
                        if f.get("agent") == agent_name:
                            agent_specific_context["reviewer_feedback"] = f.get(
                                "feedback"
                            )
                            self.logger.info(
                                "Injecting peer review feedback", agent=agent_name
                            )

                    state = set_agent_state(state, agent_name, AgentState.RUNNING)
                    task = self._run_agent_with_timeout(
                        agent, agent_specific_context, agent_name, output_key
                    )
                    tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for (agent_name, output_key), result in zip(agents_to_run, results):
                if isinstance(result, Exception):
                    self.logger.error(f"Agent {agent_name} failed", error=str(result))
                    state = set_agent_state(state, agent_name, AgentState.ERROR)
                else:
                    agent_name, output_key, output_data = result
                    if output_data:
                        state = update_state(state, {output_key: output_data})
                        state = set_agent_state(state, agent_name, AgentState.COMPLETED)

        else:
            # Run agents sequentially
            for agent_name, output_key in agents_to_run:
                agent = self.agent_registry.get(agent_name)
                if agent:
                    # Inject specific feedback for this agent
                    agent_specific_context = context.copy()
                    for f in peer_feedback:
                        if f.get("agent") == agent_name:
                            agent_specific_context["reviewer_feedback"] = f.get(
                                "feedback"
                            )
                            self.logger.info(
                                "Injecting peer review feedback", agent=agent_name
                            )

                    state = set_agent_state(state, agent_name, AgentState.RUNNING)
                    try:
                        result = await agent.run(
                            f"Analyze {agent_name.replace('_', ' ')} aspects",
                            context=agent_specific_context,
                        )

                        if result.success:
                            state = update_state(state, {output_key: result.data})
                            state = set_agent_state(
                                state, agent_name, AgentState.COMPLETED
                            )
                        else:
                            state = set_agent_state(state, agent_name, AgentState.ERROR)

                    except Exception as e:
                        self.logger.error(f"Agent {agent_name} failed", error=str(e))
                        state = set_agent_state(state, agent_name, AgentState.ERROR)

        return state

    async def _node_consistency_check(self, state: DealState) -> DealState:
        """Run HaluGate cross-agent consistency check (QA Flow 3)"""
        self.logger.info("Running consistency check", deal_id=state["deal_id"])

        agent_outputs = {
            "financial_analyst": state.get("financial_output", {}),
            "legal_advisor": state.get("legal_output", {}),
            "risk_assessor": state.get("risk_output", {}),
            "market_researcher": state.get("market_output", {}),
        }

        try:
            warnings = self.halugate.cross_agent_verify(agent_outputs, check_point=1)

            if warnings:
                existing = state.get("consistency_warnings") or []
                existing.extend(warnings)
                state = update_state(state, {"consistency_warnings": existing})

                self.logger.warning(
                    "Consistency warnings detected",
                    count=len(warnings),
                    material=[w for w in warnings if w.get("severity") == "material"],
                )
            else:
                self.logger.info("Consistency check passed — no contradictions")

        except Exception as e:
            self.logger.error("Consistency check failed", error=str(e))

        return state

    async def _run_agent_with_timeout(
        self, agent, context: Dict, agent_name: str, output_key: str
    ):
        """Run an agent with timeout, respecting the concurrency semaphore."""
        async with self._agent_semaphore:
            try:
                timeout = self.config.get("agent_timeout_seconds", 60)

                result = await asyncio.wait_for(
                    agent.run(
                        f"Analyze {agent_name.replace('_', ' ')} aspects",
                        context=context,
                    ),
                    timeout=timeout,
                )

                if result.success:
                    return agent_name, output_key, result.data
                else:
                    return agent_name, output_key, None

            except asyncio.TimeoutError:
                self.logger.error(f"Agent {agent_name} timed out")
                return agent_name, output_key, None
            except Exception as e:
                self.logger.error(f"Agent {agent_name} error", error=str(e))
                raise

    async def _node_advanced_financial(self, state: DealState) -> DealState:
        """Run Advanced Financial Modeler"""
        self.logger.info("Running Advanced Financial Modeler", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.DUE_DILIGENCE})

        agent = self.agent_registry.get("advanced_financial_modeler")
        if agent and state.get("financial_output"):
            try:
                ctx = state.get("context", {}).copy()
                ctx["financial_data"] = state["financial_output"].get(
                    "financial_metrics", {}
                )

                result = await agent.run(
                    "Build dynamic Excel model and advanced metrics",
                    context=ctx,
                )
                if result.success:
                    state = update_state(
                        state, {"advanced_financial_output": result.data}
                    )
            except Exception as e:
                self.logger.error("Advanced Financial Modeler failed", error=str(e))

        return state

    async def _node_data_curator(self, state: DealState) -> DealState:
        """Run Data Curator Agent"""
        self.logger.info("Running Data Curator", deal_id=state["deal_id"])

        agent = self.agent_registry.get("data_curator")
        if agent:
            try:
                ctx = state.get("context", {}).copy()
                ctx["agent_outputs"] = {
                    "financial": state.get("financial_output"),
                    "advanced_financial": state.get("advanced_financial_output"),
                    "legal": state.get("legal_output"),
                    "risk": state.get("risk_output"),
                    "market": state.get("market_output"),
                }

                result = await agent.run(
                    "Curate Data Bible",
                    context=ctx,
                )
                if result.success:
                    state = update_state(state, {"curated_data": result.data})
            except Exception as e:
                self.logger.error("Data Curator failed", error=str(e))

        return state

    async def _node_complex_reasoning(self, state: DealState) -> DealState:
        """Run Complex Reasoning Agent"""
        self.logger.info("Running Complex Reasoning", deal_id=state["deal_id"])

        agent = self.agent_registry.get("complex_reasoning")
        if agent and state.get("curated_data"):
            try:
                ctx = {"curated_data": state["curated_data"]}
                result = await agent.run(
                    "Execute Chain-of-Thought reasoning",
                    context=ctx,
                )
                if result.success:
                    state = update_state(state, {"reasoning_trace": result.data})
            except Exception as e:
                self.logger.error("Complex Reasoning failed", error=str(e))

        return state

    async def _node_report_architect(self, state: DealState) -> DealState:
        """Run Report Architect Agent"""
        self.logger.info("Running Report Architect", deal_id=state["deal_id"])

        agent = self.agent_registry.get("report_architect")
        if agent:
            try:
                ctx = state.get("context", {}).copy()
                result = await agent.run(
                    "Configure report blueprint",
                    context=ctx,
                )
                if result.success:
                    state = update_state(state, {"report_blueprint": result.data})
            except Exception as e:
                self.logger.error("Report Architect failed", error=str(e))

        return state

    async def _node_debate(self, state: DealState) -> DealState:
        """Run debate/synthesis phase"""
        self.logger.info("Running debate synthesis", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.DEBATE})
        state = add_stage_to_history(state, DealStage.DEBATE)

        # Prepare agent outputs for debate
        agent_outputs = []

        if state.get("financial_output"):
            agent_outputs.append(
                {
                    "agent": "financial_analyst",
                    "position": state["financial_output"].get(
                        "recommendation", "neutral"
                    ),
                    "key_points": state["financial_output"].get("financial_risks", []),
                    "confidence": state["financial_output"].get("confidence", 0.5),
                }
            )

        if state.get("legal_output"):
            agent_outputs.append(
                {
                    "agent": "legal_advisor",
                    "position": state["legal_output"].get(
                        "overall_legal_risk", "medium"
                    ),
                    "key_points": state["legal_output"].get("key_legal_risks", []),
                    "confidence": 0.7,
                }
            )

        if state.get("risk_output"):
            agent_outputs.append(
                {
                    "agent": "risk_assessor",
                    "position": state["risk_output"]
                    .get("risk_metrics", {})
                    .get("risk_level", "medium"),
                    "key_points": state["risk_output"].get("top_risks", []),
                    "confidence": 0.75,
                }
            )

        if state.get("market_output"):
            agent_outputs.append(
                {
                    "agent": "market_researcher",
                    "position": (
                        "positive"
                        if state["market_output"].get("market_size", {}).get("tam", 0)
                        > 1000000000
                        else "neutral"
                    ),
                    "key_points": state["market_output"].get(
                        "growth_opportunities", []
                    ),
                    "confidence": state["market_output"].get("confidence", 0.5),
                }
            )

        # Run debate moderator
        debate_agent = self.agent_registry.get("debate_moderator")
        if debate_agent and agent_outputs:
            try:
                result = await debate_agent.run(
                    "Synthesize agent perspectives on deal",
                    context={
                        "topic": f"Deal: {state['deal_name']}",
                        "agent_outputs": agent_outputs,
                    },
                )

                if result.success:
                    state = update_state(state, {"debate_output": result.data})

            except Exception as e:
                self.logger.error("Debate failed", error=str(e))

        return state

    async def _node_red_team(self, state: DealState) -> DealState:
        """Run Red Team adversarial analysis"""
        self.logger.info("Running Red Team sweep", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.RED_TEAM})
        state = add_stage_to_history(state, DealStage.RED_TEAM)

        red_team_agent = self.agent_registry.get("red_team")
        if red_team_agent:
            try:
                # Collect all agent outputs for cross-checking
                agent_outputs = {
                    "financial_analyst": state.get("financial_output", {}),
                    "legal_advisor": state.get("legal_output", {}),
                    "risk_assessor": state.get("risk_output", {}),
                    "market_researcher": state.get("market_output", {}),
                }

                result = await red_team_agent.run(
                    f"Red Team sweep for deal: {state['deal_name']}",
                    context={
                        "deal_id": state["deal_id"],
                        "issue_tree": state.get("issue_tree", {}),
                        "agent_outputs": agent_outputs,
                        "industry": state.get("context", {}).get("industry", ""),
                    },
                )

                if result.success:
                    state = update_state(
                        state,
                        {
                            "red_team_output": result.data,
                            "red_team_flags": result.data.get("flags", []),
                        },
                    )

                    # Log severity summary
                    max_sev = result.data.get("max_severity", 0)
                    total_flags = result.data.get("total_flags", 0)
                    self.logger.info(
                        "Red Team complete",
                        total_flags=total_flags,
                        max_severity=max_sev,
                        recommendation=result.data.get("recommendation", ""),
                    )

            except Exception as e:
                self.logger.error("Red Team failed", error=str(e))

        return state

    async def _node_halugate_verify(self, state: DealState) -> DealState:
        """Run HaluGate verification on scoring output"""
        self.logger.info("Running HaluGate verification", deal_id=state["deal_id"])

        scoring_output = state.get("scoring_output", {})
        financial_output = state.get("financial_output", {})

        if scoring_output and financial_output:
            try:
                # Build narrative from scoring output
                narrative_parts = []
                if scoring_output.get("recommendations"):
                    narrative_parts.extend(scoring_output["recommendations"])
                if scoring_output.get("scoring_breakdown"):
                    narrative_parts.append(str(scoring_output["scoring_breakdown"]))

                narrative = ". ".join(str(p) for p in narrative_parts)

                if narrative:
                    results = await self.halugate.verify_narrative(
                        narrative=narrative,
                        ground_truth=financial_output,
                        math_outputs=scoring_output,
                    )

                    blocked = self.halugate.should_block(results)
                    severity_summary = self.halugate.get_severity_summary(results)

                    # Store results in context
                    ctx = state.get("context", {})
                    ctx["halugate_results"] = {
                        "blocked": blocked,
                        "severity_summary": severity_summary,
                        "total_claims_checked": len(results),
                        "verdicts": [
                            {
                                "claim": r.claim[:100],
                                "verdict": r.verdict.value,
                                "severity": r.severity.value,
                            }
                            for r in results
                        ],
                    }
                    state = update_state(state, {"context": ctx})

                    if blocked:
                        self.logger.error(
                            "HaluGate BLOCKED — narrative contradicts financial data",
                            severity=severity_summary,
                        )
                        state = update_state(
                            state,
                            {
                                "final_recommendation": "BLOCKED — HaluGate detected narrative-math contradiction. Escalated to human review.",
                            },
                        )

            except Exception as e:
                self.logger.error("HaluGate verification failed", error=str(e))

        return state

    async def _node_scoring(self, state: DealState) -> DealState:
        """Calculate final deal score"""
        self.logger.info("Running scoring", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.SCORING})
        state = add_stage_to_history(state, DealStage.SCORING)

        # Run scoring agent
        scoring_agent = self.agent_registry.get("scoring_agent")
        if scoring_agent:
            try:
                result = await scoring_agent.run(
                    "Calculate final deal score",
                    context={
                        "deal_id": state["deal_id"],
                        "financial_output": state.get("financial_output"),
                        "legal_output": state.get("legal_output"),
                        "risk_output": state.get("risk_output"),
                        "market_output": state.get("market_output"),
                    },
                )

                if result.success:
                    state = update_state(state, {"scoring_output": result.data})
                    state = update_state(
                        state, {"final_score": result.data.get("total_score")}
                    )

            except Exception as e:
                self.logger.error("Scoring failed", error=str(e))

        return state

    async def _node_report_formatting(self, state: DealState) -> DealState:
        """Run Business Analyst to format the final delivery payload"""
        self.logger.info("Running report formatting", deal_id=state["deal_id"])

        ba_agent = self.agent_registry.get("business_analyst")
        if ba_agent:
            try:
                # Prepare all agent outputs
                agent_data = {
                    "financial": state.get("financial_output"),
                    "legal": state.get("legal_output"),
                    "risk": state.get("risk_output"),
                    "market": state.get("market_output"),
                    "debate": state.get("debate_output"),
                    "red_team": state.get("red_team_output"),
                }

                result = await ba_agent.run(
                    "Format report payload",
                    context={"deal_id": state["deal_id"], "deal_data": agent_data},
                )
                if result.success:
                    state = update_state(state, {"analyst_output": result.data})
            except Exception as e:
                self.logger.error("Report formatting failed", error=str(e))

        return state

    async def _node_compiler(self, state: DealState) -> DealState:
        """Run the Report Compiler Agent to write physical files"""
        self.logger.info("Running report compilation", deal_id=state["deal_id"])

        compiler_agent = self.agent_registry.get("compiler_agent")
        if compiler_agent:
            try:
                # Prepare all agent outputs for the compiler
                agent_results = []
                for k in [
                    "financial_output",
                    "legal_output",
                    "risk_output",
                    "market_output",
                    "red_team_output",
                ]:
                    if state.get(k):
                        agent_results.append(
                            {
                                "agent_type": k.replace("_output", ""),
                                "data": state[k],
                                "reasoning": state[k].get("reasoning", ""),
                                "confidence": state[k].get("confidence", 0.5),
                            }
                        )

                # Need core deal mapping
                deal_info = {
                    "id": state["deal_id"],
                    "name": state.get("deal_name"),
                    "target_company": state.get("context", {}).get("target_company"),
                    "industry": state.get("context", {}).get("industry"),
                    "final_score": state.get("final_score"),
                    "status": "completed",
                    "created_at": state.get("started_at"),
                }

                # Construct execution context
                ctx = {
                    "formats": ["pptx", "excel"],  # Default deliverables
                    "deal_state": {
                        "deal_name": deal_info.get("name"),
                        "target_company": deal_info.get("target_company"),
                        "final_score": state.get("final_score"),
                        "agents_run": [r["agent_type"] for r in agent_results],
                    },
                }

                # Run compilation
                result = await compiler_agent.run(
                    "Compile the final deliverables for this deal", context=ctx
                )

                if result.success:
                    # Write files out to disk from Base64
                    import base64
                    import os

                    data = result.data
                    files = data.get("files_base64", {})
                    out_paths = []

                    from app.config import get_settings

                    settings = get_settings()
                    reports_dir = os.path.join(settings.REPORTS_DIR, state["deal_id"])
                    os.makedirs(reports_dir, exist_ok=True)

                    for ext, b64_data in files.items():
                        path = os.path.join(
                            reports_dir,
                            f"{deal_info.get('target_company', 'Deal').replace(' ', '_')}_Report.{ext}",
                        )
                        with open(path, "wb") as f:
                            f.write(base64.b64decode(b64_data))
                        out_paths.append(path)
                        self.logger.info("Report compiled and saved", file=path)

                    state = update_state(
                        state,
                        {"compiler_output": result.data, "generated_files": out_paths},
                    )

            except Exception as e:
                self.logger.error("Report compilation failed", error=str(e))

        return state

    async def _node_decision(self, state: DealState) -> DealState:
        """Generate final decision"""
        self.logger.info("Generating decision", deal_id=state["deal_id"])

        state = update_state(state, {"current_stage": DealStage.DECISION})
        state = add_stage_to_history(state, DealStage.DECISION)

        # Generate recommendation based on score
        score = state.get("final_score", 0)
        scoring_output = state.get("scoring_output", {})
        risk_level = scoring_output.get("risk_level", "medium")

        if score >= 75 and risk_level in ["low", "moderate"]:
            recommendation = "PROCEED - Strong investment opportunity"
        elif score >= 60 and risk_level in ["low", "moderate", "high"]:
            recommendation = "PROCEED WITH CAUTION - Address identified risks"
        elif score >= 40:
            recommendation = "HOLD - Requires further due diligence"
        else:
            recommendation = "REJECT - Does not meet investment criteria"

        state = update_state(state, {"final_recommendation": recommendation})

        return state

    async def _node_error_handler(self, state: DealState) -> DealState:
        """Handle errors in workflow"""
        self.logger.error("Handling workflow error", deal_id=state["deal_id"])

        error_agents = get_error_agents(state)

        # Check if we should retry
        retry_count = state.get("retry_count", 0)
        max_retries = 2

        if retry_count < max_retries:
            return update_state(
                state,
                {
                    "retry_count": retry_count + 1,
                    "error_message": f"Retrying after errors from: {', '.join(error_agents)}",
                },
            )
        else:
            return update_state(
                state,
                {
                    "error_message": f"Max retries exceeded. Failed agents: {', '.join(error_agents)}",
                    "final_recommendation": "ERROR - Workflow failed",
                },
            )

    async def _node_complete(self, state: DealState) -> DealState:
        """Complete the workflow and flush provenance to DB."""
        self.logger.info("Completing workflow", deal_id=state["deal_id"])

        # Flush real-time provenance to persistent DB
        try:
            from app.core.provenance import get_provenance_collector

            count = await get_provenance_collector().flush_to_postgres(state["deal_id"])
            self.logger.info(f"Flushed {count} provenance records to DB")
        except Exception as e:
            self.logger.error("Provenance DB flush failed", error=str(e))

        return update_state(
            state,
            {
                "current_stage": DealStage.COMPLETED,
                "completed_at": datetime.utcnow().isoformat(),
            },
        )

    # ===== Conditional Edge Functions =====

    def _should_continue_to_screening(self, state: DealState) -> str:
        """Determine if we should proceed to screening"""
        if state.get("error_message"):
            return "error"
        return "screening"

    def _should_continue_to_analysis(self, state: DealState) -> str:
        """Determine if we should proceed to analysis"""
        if state.get("error_message"):
            if "REJECT" in state.get("final_recommendation", ""):
                return "reject"
            return "error"
        return "analysis"

    def _should_continue_to_advanced_financial(self, state: DealState) -> str:
        """Determine if we should proceed to Advanced Financial Modeler"""
        if has_errors(state):
            return "error"
        required = ["financial_analyst", "legal_advisor", "risk_assessor"]
        if not all_agents_completed(state, required):
            return "wait"
        return "advanced_financial"

    def _should_continue_to_data_curator(self, state: DealState) -> str:
        if has_errors(state):
            return "error"
        return "data_curator"

    def _should_continue_to_complex_reasoning(self, state: DealState) -> str:
        if has_errors(state):
            return "error"
        return "complex_reasoning"

    def _should_continue_to_report_formatting(self, state: DealState) -> str:
        if has_errors(state):
            return "error"
        return "report_formatting"

    def _should_continue_to_debate(self, state: DealState) -> str:
        """Determine if we should proceed to debate"""
        if has_errors(state):
            return "error"
        return "debate"

    def _should_continue_to_scoring(self, state: DealState) -> str:
        """Determine if we should proceed to scoring"""
        if has_errors(state):
            return "error"
        return "scoring"

    def _should_continue_after_debate(self, state: DealState) -> str:
        """After debate (Peer Review): proceed to Red Team or loop back if revisions are required"""
        if has_errors(state):
            return "error"

        debate_output = state.get("debate_output", {})
        if debate_output.get("requires_revision", False):
            self.logger.info(
                "Peer Review requested revisions. Looping back to analysis agents.",
                deal_id=state["deal_id"],
            )
            return "loop_back"

        return "red_team"

    def _should_continue_after_red_team(self, state: DealState) -> str:
        """After Red Team: loop back if severity >= 3, otherwise proceed to scoring"""
        if has_errors(state):
            return "error"

        red_team_output = state.get("red_team_output", {})
        max_severity = red_team_output.get("max_severity", 0)
        requires_loop = red_team_output.get("requires_loop_back", False)

        if requires_loop and max_severity >= 3:
            # Only loop back once to avoid infinite cycles
            stage_history = state.get("stage_history", [])
            red_team_count = sum(
                1 for s in stage_history if s == DealStage.RED_TEAM or s == "red_team"
            )
            if red_team_count < 2:
                self.logger.warning(
                    "Red Team loop-back triggered", severity=max_severity
                )
                return "loop_back"

        return "scoring"

    def _should_continue_to_halugate(self, state: DealState) -> str:
        """After scoring, run HaluGate verification"""
        if has_errors(state):
            return "error"
        return "halugate"

    def _should_continue_after_halugate(self, state: DealState) -> str:
        """After HaluGate: proceed to report_architect or escalate if blocked"""
        if has_errors(state):
            return "error"

        halugate_data = state.get("context", {}).get("halugate_results", {})
        if halugate_data.get("blocked", False):
            self.logger.error("HaluGate BLOCKED output — escalating")
            return "escalate"

        return "report_architect"

    def _should_continue_to_compiler(self, state: DealState) -> str:
        """Determine if we should proceed to compiler"""
        if has_errors(state):
            return "error"
        return "compiler"

    def _should_continue_to_decision(self, state: DealState) -> str:
        """Determine if we should proceed to decision"""
        if has_errors(state):
            return "error"
        return "decision"

    def _should_complete(self, state: DealState) -> str:
        """Determine if workflow should complete"""
        if state.get("error_message") and not state.get("final_recommendation"):
            return "error"
        return "complete"

    def _handle_error_decision(self, state: DealState) -> str:
        """Decide how to handle errors"""
        retry_count = state.get("retry_count", 0)
        max_retries = 2

        if retry_count < max_retries:
            return "retry"
        return "complete"

    # ===== Public API =====

    async def run_deal(
        self, deal_id: str, deal_name: str, context: Dict[str, Any] = None
    ) -> DealState:
        """
        Run complete deal workflow

        Args:
            deal_id: Unique deal identifier
            deal_name: Deal name
            context: Initial context data

        Returns:
            Final workflow state
        """
        self.logger.info("Starting deal workflow", deal_id=deal_id, deal_name=deal_name)

        # Create initial state
        initial_state = create_initial_state(deal_id, deal_name, context)

        # Run the graph
        # Note: LangGraph 0.0.48 uses ainvoke for async
        try:
            run_config = {
                "recursion_limit": self.config.get("max_iterations", 10),
                "configurable": {"thread_id": str(deal_id)},
            }
            self.logger.info("Calling graph.ainvoke with config:", config=run_config)

            final_state = await self.graph.ainvoke(
                initial_state,
                config=run_config,
            )

            self.logger.info(
                "Workflow completed",
                deal_id=deal_id,
                final_stage=final_state.get("current_stage"),
                recommendation=final_state.get("final_recommendation"),
            )

            return final_state

        except Exception as e:
            import traceback

            err_trace = traceback.format_exc()
            print(f"CRITICAL WORKFLOW ERROR:\n{err_trace}")
            self.logger.error(
                "Workflow failed", deal_id=deal_id, error=str(e), traceback=err_trace
            )

            return update_state(
                initial_state,
                {
                    "current_stage": DealStage.ERROR,
                    "error_message": str(e),
                    "final_recommendation": "ERROR - Workflow execution failed",
                },
            )


# Singleton orchestrator instance
_orchestrator: Optional[DealOrchestrator] = None


def get_orchestrator(config: Optional[WorkflowConfig] = None) -> DealOrchestrator:
    """Get or create orchestrator singleton"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DealOrchestrator(config)
    return _orchestrator
