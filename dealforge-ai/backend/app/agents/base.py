"""Base Agent Class for DealForge AI"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import structlog
import json

from app.core.llm import get_llm_client
from app.core.llm.model_router import get_model_router
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
        if skill_context:
            self.logger.info(
                "Skill injected", agent=self.name, skill_chars=len(skill_context)
            )
            # Pass skill to the LLM context via enriched_context
            context = {**(context or {}), "skill_context": skill_context}

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
        self, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context from memory"""
        try:
            chunks = await self.memory.query(query, top_k=top_k)
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
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate response with potential tool calls"""
        from app.core.llm.model_router import get_model_router

        # Get available tools (filtered per-agent via AGENT_TOOL_MAP)
        tools = self.tools.list_tools(agent_name=self.name)

        # Get fresh router to respect dynamic UI settings changes
        llm = get_model_router().get_client_for_agent(self.name)

        # Generate initial response
        response = await llm.generate(
            prompt=prompt, system_prompt=system_prompt, tools=tools if tools else None
        )

        # Handle tool calls
        if response.get("function_calls"):
            self.logger.info(
                "Tool calls detected",
                calls=[c["name"] for c in response["function_calls"]],
            )

            # Execute tools
            tool_results = await self.tools.execute_function_calls(
                response["function_calls"]
            )

            # Add tool results to response
            response["tool_results"] = [
                {"success": r.success, "data": r.data, "error": r.error}
                for r in tool_results
            ]

            import json

            tool_context = json.dumps(response["tool_results"], indent=2)
            follow_up = f"{prompt}\n\n--- TOOL EXECUTION RESULTS ---\n{tool_context}\n\nBased on these results, provide your final comprehensive analysis in the requested JSON format. Ensure your output is purely JSON."

            final_response = await llm.generate(
                prompt=follow_up, system_prompt=system_prompt
            )
            response["content"] = final_response.get("content", "")

        return response

    def build_system_prompt(self) -> str:
        """Build system prompt for the agent"""
        return f"""You are {self.name}, {self.description}.

Your task is to provide thorough, well-reasoned analysis with specific data points and actionable recommendations.

Guidelines:
- Always show your reasoning process
- Cite specific data and sources
- Provide actionable recommendations
- Be objective and highlight both positives and concerns
- Format output as structured JSON when requested
"""

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
            from app.core.llm.model_router import get_model_router

            llm = get_model_router().get_client_for_agent(self.name)

            response = await llm.generate(
                prompt=tree_prompt,
                system_prompt="You are a McKinsey-trained structured problem solver. Return only valid JSON.",
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
        """Get agent by name"""
        return self.agents.get(name)

    def list_agents(self) -> List[Dict[str, str]]:
        """List all registered agents"""
        return [
            {"name": name, "description": agent.description}
            for name, agent in self.agents.items()
        ]


# Global registry
_agent_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get global agent registry"""
    return _agent_registry
