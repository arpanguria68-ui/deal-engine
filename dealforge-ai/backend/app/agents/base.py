"""Base Agent Class for DealForge AI"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import structlog
import json
import re
import asyncio

from app.core.llm import get_llm_client
from app.core.llm.model_router import get_model_router
from app.core.llm.llm_gateway import get_llm_gateway
from app.core.memory.pageindex_client import PageIndexClient
from app.core.tools.tool_router import ToolRouter
from app.core.reflection.reflection_engine import ReflectionEngine, RewardEngine
from app.core.skills import build_skill_context, get_skill_for_task
from app.core.validation.output_validator import (
    validate_agent_output,
    format_validation_block,
)

logger = structlog.get_logger()


@dataclass
class IssueTreeNode:
    """A node in a MECE issue tree"""

    id: str
    hypothesis: str
    sub_branches: List["IssueTreeNode"] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    status: str = "open"  # open, supported, refuted, needs_data
    confidence: float = 0.0


@dataclass
class AgentOutput:
    """Standardized agent output"""

    success: bool
    data: Dict[str, Any]
    reasoning: str
    confidence: float
    execution_time_ms: Optional[float] = None
    tool_calls: Optional[List[Dict]] = None
    reflection_score: Optional[float] = None
    issue_tree: Optional[Dict] = None


class BaseAgent(ABC):
    """Base class for all DealForge agents"""

    name: str = "base_agent"
    description: str = "Base agent class"
    recommended_model: str = ""

    def __init__(
        self,
        llm_client=None,
        pageindex_client=None,
        tool_router=None,
        reflection_engine=None,
        reward_engine=None,
    ):
        # Use ModelRouter for mixed cloud+local LLM strategy
        if llm_client:
            self.llm = llm_client
        else:
            router = get_model_router()
            self.llm = router.get_client_for_agent(self.name)
        self.memory = pageindex_client or PageIndexClient()
        self.pageindex_client = self.memory  # Alias for legacy agent support
        self.reflection = reflection_engine or ReflectionEngine()
        self.reward = reward_engine or RewardEngine()

        # Fix: Register default tools if no custom router provided
        if tool_router:
            self.tools = tool_router
        else:
            self.tools = ToolRouter()
            self.tools.register_default_tools(self.memory)

        self.logger = structlog.get_logger(agent=self.name)

    @abstractmethod
    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute agent task

        Args:
            task: The task description
            context: Optional context data

        Returns:
            AgentOutput with results
        """
        pass

    async def run_with_structure(
        self, task: str, context: Optional[Dict] = None
    ) -> AgentOutput:
        """
        DealForge 2.0 structured execution flow:
        0. [NEW] Inject Domain Skill for this task type
        1. Generate MECE Issue Tree (hypothesis-first)
        2. Validate MECE completeness
        3. Retrieve context per branch
        4. Execute analysis with tools
        5. [NEW] Validate financial output for mathematical consistency
        6. Store learnings to memory
        """
        start_time = datetime.now()
        self.logger.info("Starting structured analysis", task=task, agent=self.name)

        # Step 0: DealForge 2.0 — Inject Domain Skill
        skill_context = build_skill_context(task, self.name)

        # [NEW] Step 0.5: Sector Customization Framework
        from app.core.sector_loader import load_sector_config, build_sector_prompt

        sector_name = (context or {}).get("sector")
        sector_prompt = ""
        if sector_name:
            cfg = load_sector_config(sector_name)
            sector_prompt = build_sector_prompt(self.name, cfg)

        if skill_context or sector_prompt:
            self.logger.info(
                "Context injection",
                agent=self.name,
                has_skill=bool(skill_context),
                has_sector=bool(sector_prompt),
            )
            # Pass injected traits to the LLM context via enriched_context
            context = {
                **(context or {}),
                "skill_context": skill_context,
                "sector_prompt": sector_prompt,
            }

        self._current_context = context  # Store centrally for generate_with_tools

        # Step 1: Generate MECE Issue Tree
        issue_tree = await self.generate_issue_tree(task, context)
        self.logger.info("Issue tree generated", branches=len(issue_tree.sub_branches))

        # Step 2: Validate MECE
        is_valid, gaps = self.validate_mece(issue_tree)
        if not is_valid:
            self.logger.warning("MECE validation failed", gaps=gaps)
            for gap in gaps:
                issue_tree.sub_branches.append(
                    IssueTreeNode(
                        id=f"auto_{len(issue_tree.sub_branches)}", hypothesis=gap
                    )
                )

        # Step 3: Retrieve context per branch
        branch_contexts = {}
        for branch in issue_tree.sub_branches:
            branch_contexts[branch.id] = await self.retrieve_context(
                branch.hypothesis, top_k=3
            )

        # Step 4: Execute the core run() with enriched context
        enriched_context = {
            **(context or {}),
            "issue_tree": self._serialize_tree(issue_tree),
            "branch_contexts": branch_contexts,
        }
        output = await self.run(task, enriched_context)

        # Step 5: DealForge 2.0 — Deterministic Output Validation
        output = await self._validate_and_annotate_output(task, output)

        # Step 6: Attach issue tree to output
        output.issue_tree = self._serialize_tree(issue_tree)

        # Step 7: Store learnings to memory
        if output.success:
            await self.store_to_memory(
                content=f"[{self.name}] {task}: {output.reasoning[:500]}",
                tags=[
                    self.name,
                    context.get("industry", "unknown") if context else "unknown",
                ],
            )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        output.execution_time_ms = execution_time
        return output

    async def _validate_and_annotate_output(
        self, task: str, output: "AgentOutput"
    ) -> "AgentOutput":
        """DealForge 2.0: Validate financial model outputs for math consistency."""
        try:
            task_lower = task.lower()
            output_data = output.data or {}

            # Determine what type of financial model was produced
            if any(
                k in task_lower for k in ["dcf", "wacc", "terminal value", "intrinsic"]
            ):
                result = validate_agent_output("dcf", output_data)
            elif any(
                k in task_lower for k in ["lbo", "leveraged buyout", "irr", "moic"]
            ):
                result = validate_agent_output("lbo", output_data)
            elif any(
                k in task_lower
                for k in ["income statement", "balance sheet", "3-statement"]
            ):
                result = validate_agent_output("financial_statement", output_data)
            else:
                return output  # No validation needed for non-numeric outputs

            # Append validation block to the reasoning
            validation_note = format_validation_block(result)
            output.reasoning = (output.reasoning or "") + validation_note
            output.data["_validation"] = result

        except Exception as e:
            self.logger.warning("output_validation_error", error=str(e))

        return output

    async def retrieve_context(
        self, query: str, top_k: int = 5, deal_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context from memory, filtered by deal_id when provided"""
        try:
            kwargs = {"top_k": top_k}
            if deal_id:
                kwargs["filters"] = {"deal_id": deal_id}
            chunks = await self.memory.query(query, **kwargs)
            return [
                {
                    "content": chunk.content,
                    "page": chunk.page_number,
                    "relevance": chunk.relevance_score,
                }
                for chunk in chunks
            ]
        except Exception as e:
            self.logger.error("Context retrieval failed", error=str(e))
            return []

    async def generate_with_tools(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tool_rounds: int = 3,
    ) -> Dict[str, Any]:
        """Generate response with tool calls, routed through LLM Gateway.

        Supports iterative multi-round tool calling (up to max_tool_rounds).
        All LLM calls go through the gateway for rate limiting, caching, and fallback.
        """
        from app.core.llm.model_router import get_model_router

        # enforce deterministic default
        if temperature is None:
            temperature = 0.0

        # Get available tools (filtered per-agent via AGENT_TOOL_MAP)
        tools = self.tools.list_tools(agent_name=self.name)

        # Inject Sector Prompt dynamically
        ctx = getattr(self, "_current_context", {})
        sector_prompt = ctx.get("sector_prompt")
        if sector_prompt:
            system_prompt = (system_prompt or "") + "\n\n" + sector_prompt

        # Get provider from router (respects UI settings)
        model_router = get_model_router()
        provider = model_router.get_provider_for_agent(self.name)
        is_local_model = provider in ["ollama", "lmstudio", "mistral"]

        gateway = get_llm_gateway()

        # For local models, inject ReAct instructions and disable native tools
        effective_tools = tools if (tools and not is_local_model) else None
        if is_local_model and tools:
            react_instructions = """
You have access to the following tools:
{}

To use a tool, you MUST output a JSON block wrapped in Markdown like this:
```json
{{
  "command": "tool_name",
  "args": {{"arg1": "value1"}}
}}
```
Do NOT wrap the JSON in any other formatting. Output only the JSON block to use a tool, or your final answer if no tools are needed.
""".format(
                json.dumps([t.get("function") for t in tools], indent=2)
            )
            system_prompt = (system_prompt or "") + "\n\n" + react_instructions

        # ── Multi-round tool calling loop (up to max_tool_rounds) ──
        accumulated_tool_results = []
        all_function_calls = []
        current_prompt = prompt
        response = {}

        for round_num in range(1, max_tool_rounds + 1):
            # Route through LLM Gateway (rate limit, cache, fallback)
            response = await gateway.call(
                provider=provider,
                prompt=current_prompt,
                system_prompt=system_prompt,
                tools=effective_tools,
                temperature=temperature,
            )

            # Parse ReAct JSON for local models
            if is_local_model and tools:
                content = response.get("content", "")
                print(f"DEBUG - Raw Local Content:\n{content}\n" + "="*40)
                # Attempt to find JSON blocks both with and without code blocks
                json_blocks = re.findall(
                    r"```json\s*(\{.*?\})\s*```", content, re.DOTALL
                )
                if not json_blocks:
                    # Fallback: look for any { } block that looks like it might be a tool call
                    json_blocks = re.findall(
                        r"(\{.*?\})", content, re.DOTALL
                    )
                function_calls = []
                for block in json_blocks:
                    try:
                        parsed = json.loads(block)
                        # Be flexible with tool call keys
                        tool_name = parsed.get("command") or parsed.get("tool") or parsed.get("name") or parsed.get("call")
                        if tool_name and isinstance(tool_name, str):
                            args = parsed.get("args") or parsed.get("parameters") or parsed.get("params") or {}
                            
                            # If args is a string, it might be double-encoded JSON
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    pass
                                    
                            function_calls.append(
                                {
                                    "name": tool_name,
                                    "args": args if isinstance(args, dict) else {},
                                }
                            )
                    except json.JSONDecodeError:
                        # Attempt JSON repair for common local LLM issues
                        try:
                            repaired = block.rstrip(",").rstrip()
                            if not repaired.endswith("}"):
                                repaired += "}"
                            parsed = json.loads(repaired)
                            tool_name = parsed.get("command") or parsed.get("tool") or parsed.get("name") or parsed.get("call")
                            if tool_name and isinstance(tool_name, str):
                                args = parsed.get("args") or parsed.get("parameters") or parsed.get("params") or {}
                                
                                # If args is a string, it might be double-encoded JSON
                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except:
                                        pass
                                        
                                function_calls.append(
                                    {
                                        "name": tool_name,
                                        "args": args if isinstance(args, dict) else {},
                                    }
                                )
                            self.logger.info("JSON repair succeeded for ReAct block")
                        except json.JSONDecodeError:
                            self.logger.warning(
                                "Failed to parse/repair ReAct JSON block", block=block
                            )
                if function_calls:
                    response["function_calls"] = function_calls

            # Check if tool calls were requested
            if not response.get("function_calls"):
                break  # No more tool calls needed — exit loop

            self.logger.info(
                "Tool calls detected",
                round=round_num,
                calls=[c["name"] for c in response["function_calls"]],
            )

            # Execute tools
            tool_results = await self.tools.execute_function_calls(
                response["function_calls"]
            )

            round_results = []
            for i, r in enumerate(tool_results):
                round_results.append({
                    "name": response["function_calls"][i]["name"],
                    "success": r.success,
                    "data": r.data,
                    "error": r.error
                })
            accumulated_tool_results.extend(round_results)
            all_function_calls.extend(response["function_calls"])

            # Build follow-up prompt with accumulated results
            tool_context = json.dumps(accumulated_tool_results, indent=2)
            current_prompt = (
                f"{prompt}\n\n--- TOOL EXECUTION RESULTS (Round {round_num}) ---\n"
                f"{tool_context}\n\n"
                f"Based on these results, either request additional tool calls if you need more data, "
                f"or provide your final comprehensive analysis in the requested JSON format."
            )

        # If we did tool calls, do a final synthesis through the gateway
        if accumulated_tool_results:
            tool_context = json.dumps(accumulated_tool_results, indent=2)
            final_prompt = (
                f"{prompt}\n\n--- ALL TOOL RESULTS ---\n{tool_context}\n\n"
                f"Based on all these results, provide your final comprehensive analysis "
                f"in the requested JSON format. Ensure your output is purely JSON."
            )
            final_response = await gateway.call(
                provider=provider,
                prompt=final_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )
            response["content"] = final_response.get("content", "")
            response["tool_results"] = accumulated_tool_results
            response["function_calls"] = all_function_calls
            response["provider_used"] = final_response.get("provider_used", provider)

        return response

    # ═══════════════════════════════════════════════════════════
    #  Stage-Aware Prompt Injection (QA Flow 1 & 5)
    # ═══════════════════════════════════════════════════════════

    _STAGE_INSTRUCTIONS = {
        "screening": (
            "\n\n## Output Format (Screening Mode)\n"
            "Focus on go/no-go signals. Limit output to 1-page equivalent. "
            "Key metrics + 3 bullet risks + recommendation signal."
        ),
        "deep_dive": (
            "\n\n## Output Format (Deep-Dive Mode)\n"
            "Provide exhaustive evidence-backed analysis. Include data tables, "
            "sourced claims, risk matrix. Every quantitative claim must cite "
            "[Source: tool_name, date]."
        ),
        "ic_memo": (
            "\n\n## Output Format (IC Memo Mode)\n"
            "Structure using Pyramid Principle: lead with recommendation, then "
            "supporting arguments, then evidence. Use SCQA framework for "
            "executive summary (Situation → Complication → Question → Answer)."
        ),
    }

    _CITATION_DISCIPLINE = (
        "\n\n## Citation Discipline\n"
        "Every quantitative claim must be followed by [Source: tool_name, date]. "
        "If data is not available from tools, explicitly mark as [ESTIMATED] "
        "and state the estimation methodology."
    )

    def build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Build system prompt with deal-stage-aware formatting instructions."""
        base = f"""You are {self.name}, {self.description}.

Your task is to provide thorough, well-reasoned analysis with specific data points and actionable recommendations.

Guidelines:
- Always show your reasoning process
- Cite specific data and sources
- Provide actionable recommendations
- Be objective and highlight both positives and concerns
- Format output as structured JSON when requested
"""
        if not context:
            return base + self._CITATION_DISCIPLINE

        # Inject buyer thesis and deal goal
        thesis = context.get("buyer_thesis")
        goal = context.get("deal_goal")
        if thesis:
            base += f"\n\n## Investment Thesis\n{thesis}"
        if goal:
            base += f"\n\n## Deal Goal\n{goal}"

        # Inject stage-specific formatting
        stage = context.get("deal_stage", "deep_dive")
        stage_instruction = self._STAGE_INSTRUCTIONS.get(
            stage, self._STAGE_INSTRUCTIONS["deep_dive"]
        )
        base += stage_instruction

        # Always append citation discipline
        base += self._CITATION_DISCIPLINE

        return base

    def validate_output(
        self, output: Dict[str, Any], expected_schema: Optional[Dict] = None
    ) -> tuple[bool, Optional[str]]:
        """Validate agent output against expected schema"""
        if not expected_schema:
            return True, None

        required_fields = expected_schema.get("required", [])
        missing = [f for f in required_fields if f not in output]

        if missing:
            return False, f"Missing required fields: {missing}"

        return True, None

    async def reflect(
        self, task: str, output: AgentOutput, expected_schema: Optional[Dict] = None
    ) -> float:
        """Run reflection on agent output"""
        reflection_result = self.reflection.evaluate(
            task=task, agent_output=output.data, expected_format=expected_schema
        )

        self.logger.info(
            "Reflection complete",
            score=reflection_result.score,
            grade=reflection_result.grade.value,
        )

        return reflection_result.score

    # ===== MECE Issue Tree Methods =====

    async def evaluate_replication(
        self, task: str, context: Optional[Dict] = None, runs: int = 3
    ) -> Dict[str, float]:
        """Execute the same task multiple times and return consistency metrics.

        This utility is intended for quality assessments and can optionally log
        the results to the AgentQualityStore. By default the underlying LLM is
        invoked with temperature=0 (deterministic), but stochastic models will
        still vary, allowing us to quantify variance.
        """
        from app.core.quality.replication import evaluate_outputs
        from app.core.quality.agent_quality_store import AgentQualityStore

        outputs: list[str] = []
        for _ in range(runs):
            result = await self.run(task, context)
            outputs.append(str(result.data or result.reasoning or result))

        stats = evaluate_outputs(outputs)

        # log into quality store for later inspection
        try:
            store = AgentQualityStore()
            await store.initialize()
            await store.log_replication_run(self.name, task, outputs)
        except Exception:
            # best-effort, do not fail entire evaluation
            self.logger.warning("replication_logging_failed")

        return stats

    async def generate_issue_tree(
        self, task: str, context: Optional[Dict] = None
    ) -> IssueTreeNode:
        """
        Generate a MECE (Mutually Exclusive, Collectively Exhaustive) issue tree.
        Every analysis starts with a hypothesis and branches into sub-questions.
        """
        tree_prompt = f"""You are generating a MECE issue tree for the following analysis task.

Task: {task}
Context: {json.dumps(context or {}, indent=2, default=str)}

Generate a hypothesis-first issue tree with 3-6 MECE branches. Each branch must be:
1. Mutually Exclusive: No overlap between branches
2. Collectively Exhaustive: Together they cover the entire problem space

Respond with JSON:
{{
    "hypothesis": "Main hypothesis statement",
    "branches": [
        {{
            "id": "branch_1",
            "hypothesis": "Sub-hypothesis",
            "key_questions": ["What data is needed?", "What metrics matter?"]
        }}
    ]
}}"""

        try:
            llm = get_model_router().get_client_for_agent(self.name)
            provider = get_model_router().get_provider_for_agent(self.name)

            response = await get_llm_gateway().call(
                provider=provider,
                prompt=tree_prompt,
                system_prompt="You are a McKinsey-trained structured problem solver. Return only valid JSON.",
                temperature=0.0,
            )
            tree_data = json.loads(
                response["content"].strip().strip("```json").strip("```").strip()
            )

            root = IssueTreeNode(
                id="root",
                hypothesis=tree_data.get("hypothesis", task),
            )
            for branch in tree_data.get("branches", []):
                root.sub_branches.append(
                    IssueTreeNode(
                        id=branch.get("id", f"branch_{len(root.sub_branches)}"),
                        hypothesis=branch.get("hypothesis", ""),
                        evidence=branch.get("key_questions", []),
                    )
                )
            return root

        except Exception as e:
            self.logger.error(
                "Issue tree generation failed, using fallback", error=str(e)
            )
            return IssueTreeNode(
                id="root",
                hypothesis=task,
                sub_branches=[
                    IssueTreeNode(
                        id="financial", hypothesis="Financial viability and valuation"
                    ),
                    IssueTreeNode(
                        id="strategic", hypothesis="Strategic fit and synergies"
                    ),
                    IssueTreeNode(id="risk", hypothesis="Risk factors and mitigation"),
                    IssueTreeNode(
                        id="operational",
                        hypothesis="Operational integration feasibility",
                    ),
                ],
            )

    def validate_mece(self, tree: IssueTreeNode) -> tuple[bool, List[str]]:
        """
        Validate that the issue tree is MECE.
        Returns (is_valid, list_of_gaps).
        """
        required_dimensions = {
            "financial": False,
            "strategic": False,
            "risk": False,
            "operational": False,
        }

        branch_texts = [b.hypothesis.lower() for b in tree.sub_branches]

        financial_keywords = [
            "financial",
            "valuation",
            "revenue",
            "cash flow",
            "dcf",
            "ebitda",
            "margin",
        ]
        strategic_keywords = ["strategic", "synergy", "market", "competitive", "growth"]
        risk_keywords = ["risk", "threat", "regulatory", "compliance", "legal"]
        operational_keywords = [
            "operational",
            "integration",
            "execution",
            "technology",
            "team",
        ]

        for text in branch_texts:
            if any(kw in text for kw in financial_keywords):
                required_dimensions["financial"] = True
            if any(kw in text for kw in strategic_keywords):
                required_dimensions["strategic"] = True
            if any(kw in text for kw in risk_keywords):
                required_dimensions["risk"] = True
            if any(kw in text for kw in operational_keywords):
                required_dimensions["operational"] = True

        gaps = [dim for dim, covered in required_dimensions.items() if not covered]
        return len(gaps) == 0, gaps

    def _serialize_tree(self, node: IssueTreeNode) -> Dict:
        """Serialize an IssueTreeNode to a dictionary."""
        return {
            "id": node.id,
            "hypothesis": node.hypothesis,
            "status": node.status,
            "confidence": node.confidence,
            "evidence": node.evidence,
            "sub_branches": [self._serialize_tree(b) for b in node.sub_branches],
        }

    async def store_to_memory(
        self, content: str, tags: Optional[List[str]] = None
    ) -> None:
        """
        Store learnings/insights to the MemoryEntry table for cross-deal intelligence.
        """
        try:
            await self.memory.ingest_document(
                content=content,
                metadata={
                    "agent_type": self.name,
                    "tags": tags or [],
                    "timestamp": datetime.now().isoformat(),
                },
            )
            self.logger.info("Memory stored", agent=self.name, tags=tags)
        except Exception as e:
            self.logger.warning("Failed to store memory", error=str(e))


from app.agents.compiler_agent import ReportCompilerAgent


class AgentRegistry:
    """Registry for managing agents"""

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.logger = structlog.get_logger()

    def register(self, agent: BaseAgent):
        """Register an agent"""
        self.agents[agent.name] = agent
        self.logger.info("Agent registered", agent_name=agent.name)

    def get(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name"""
        return self.agents.get(name)

    def list_agents(self) -> List[str]:
        """List registered agent names"""
        return list(self.agents.keys())


# Singleton registry instance
_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Get the singleton agent registry"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()

        # Import all agents here to avoid circular dependencies
        from app.agents.project_manager import ProjectManagerAgent
        from app.agents.market_researcher import (
            MarketResearcherAgent,
            DebateModeratorAgent,
            ScoringAgent,
        )
        from app.agents.financial_analyst import FinancialAnalystAgent, ValuationAgent
        from app.agents.risk_assessor import RiskAssessorAgent, MarketRiskAgent
        from app.agents.legal_advisor import LegalAdvisorAgent, ComplianceAgent
        from app.agents.dcf_lbo_architect import DCFLBOArchitectAgent
        from app.agents.red_team_agent import RedTeamAgent
        from app.agents.business_analyst import BusinessAnalystAgent

        # Extended agents
        from app.agents.due_diligence_agent import CommercialDueDiligenceAgent
        from app.agents.integration_planner_agent import IntegrationPlannerAgent

        # Removed missing or re-mapped agents
        from app.agents.esg_agent import ESGAgent
        from app.agents.prospectus_agent import ProspectusProcessingAgent
        from app.agents.treasury_agent import (
            TaxComplianceAgent,
            TreasuryCashAgent,
            FPAForecastingAgent,
        )
        from app.agents.ofas_supervisor import OFASSupervisorAgent
        from app.agents.ai_tech_diligence_agent import AITechDiligenceAgent
        from app.agents.compliance_qa_agent import ComplianceQAAgent
        from app.agents.investment_memo_agent import InvestmentMemoAgent
        from app.agents.compiler_agent import ReportCompilerAgent

        # New advanced agents
        from app.agents.advanced_financial_modeler import AdvancedFinancialModelerAgent
        from app.agents.data_curator_agent import DataCuratorAgent
        from app.agents.complex_reasoning_agent import ComplexReasoningAgent
        from app.agents.report_architect_agent import ReportArchitectAgent

        # Register core agents
        _registry.register(ProjectManagerAgent())
        _registry.register(DebateModeratorAgent())
        _registry.register(ScoringAgent())
        _registry.register(FinancialAnalystAgent())
        _registry.register(MarketResearcherAgent())
        _registry.register(LegalAdvisorAgent())
        _registry.register(RiskAssessorAgent())
        _registry.register(MarketRiskAgent())
        _registry.register(ComplianceAgent())
        _registry.register(DCFLBOArchitectAgent())

        # Register extended agents
        _registry.register(ValuationAgent())
        _registry.register(CommercialDueDiligenceAgent())
        _registry.register(IntegrationPlannerAgent())
        _registry.register(ESGAgent())
        _registry.register(ProspectusProcessingAgent())
        _registry.register(TaxComplianceAgent())
        _registry.register(TreasuryCashAgent())
        _registry.register(AITechDiligenceAgent())
        _registry.register(OFASSupervisorAgent())
        _registry.register(ComplianceQAAgent())
        _registry.register(InvestmentMemoAgent())
        _registry.register(ReportCompilerAgent())

        # Register advanced agents
        _registry.register(AdvancedFinancialModelerAgent())
        _registry.register(DataCuratorAgent())
        _registry.register(ComplexReasoningAgent())
        _registry.register(ReportArchitectAgent())

        # Register previously missing agents
        _registry.register(RedTeamAgent())
        _registry.register(BusinessAnalystAgent())
        _registry.register(FPAForecastingAgent())

    return _registry
