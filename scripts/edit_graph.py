import sys

with open(
    r"f:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\app\orchestrator\graph.py",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

# 1. Imports
if "DataCuratorAgent" not in content:
    content = content.replace(
        "from app.agents.compiler_agent import ReportCompilerAgent",
        "from app.agents.compiler_agent import ReportCompilerAgent\n"
        "from app.agents.data_curator_agent import DataCuratorAgent\n"
        "from app.agents.complex_reasoning_agent import ComplexReasoningAgent\n"
        "from app.agents.report_architect_agent import ReportArchitectAgent\n"
        "from app.agents.advanced_financial_modeler import AdvancedFinancialModelerAgent",
    )

# 2. Registrations
if "self.agent_registry.register(DataCuratorAgent())" not in content:
    content = content.replace(
        "self.agent_registry.register(ReportCompilerAgent())",
        "self.agent_registry.register(ReportCompilerAgent())\n"
        "        self.agent_registry.register(DataCuratorAgent())\n"
        "        self.agent_registry.register(ComplexReasoningAgent())\n"
        "        self.agent_registry.register(ReportArchitectAgent())\n"
        "        self.agent_registry.register(AdvancedFinancialModelerAgent())",
    )

# 3. Nodes in _build_graph
workflow_nodes = """        workflow.add_node("parallel_analysis", self._node_parallel_analysis)
        workflow.add_node("advanced_financial", self._node_advanced_financial)
        workflow.add_node("data_curator", self._node_data_curator)
        workflow.add_node("complex_reasoning", self._node_complex_reasoning)
        workflow.add_node("report_architect", self._node_report_architect)"""

content = content.replace(
    '        workflow.add_node("parallel_analysis", self._node_parallel_analysis)',
    workflow_nodes,
)

# 4. Edges in _build_graph
old_edge_1 = """        # From parallel analysis
        workflow.add_conditional_edges(
            "parallel_analysis",
            self._should_continue_to_debate,
            {"debate": "debate", "error": "error_handler", "wait": "parallel_analysis"},
        )"""

new_edge_1 = """        # From parallel analysis
        workflow.add_conditional_edges(
            "parallel_analysis",
            self._should_continue_to_advanced_financial,
            {"advanced_financial": "advanced_financial", "error": "error_handler", "wait": "parallel_analysis"},
        )
        
        workflow.add_conditional_edges(
            "advanced_financial",
            self._should_continue_to_data_curator,
            {"data_curator": "data_curator", "error": "error_handler"}
        )

        workflow.add_conditional_edges(
            "data_curator",
            self._should_continue_to_complex_reasoning,
            {"complex_reasoning": "complex_reasoning", "error": "error_handler"}
        )

        workflow.add_conditional_edges(
            "complex_reasoning",
            self._should_continue_to_debate,
            {"debate": "debate", "error": "error_handler"}
        )"""

content = content.replace(old_edge_1, new_edge_1)

old_edge_2 = """        # From HaluGate → report_formatting OR escalate
        workflow.add_conditional_edges(
            "halugate_verify",
            self._should_continue_after_halugate,
            {
                "report_formatting": "report_formatting",
                "escalate": "complete",
                "error": "error_handler",
            },
        )"""

new_edge_2 = """        # From HaluGate → report_architect OR escalate
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
            {"report_formatting": "report_formatting", "error": "error_handler"}
        )"""

content = content.replace(old_edge_2, new_edge_2)

# 5. Add new methods
if "async def _node_data_curator" not in content:
    methods_to_add = """
    async def _node_advanced_financial(self, state: DealState) -> DealState:
        \"\"\"Run Advanced Financial Modeler\"\"\"
        self.logger.info("Running Advanced Financial Modeler", deal_id=state["deal_id"])
        
        state = update_state(state, {"current_stage": DealStage.DUE_DILIGENCE})
        
        agent = self.agent_registry.get("advanced_financial_modeler")
        if agent and state.get("financial_output"):
            try:
                ctx = state.get("context", {}).copy()
                ctx["financial_data"] = state["financial_output"].get("financial_metrics", {})
                
                result = await agent.run(
                    "Build dynamic Excel model and advanced metrics",
                    context=ctx,
                )
                if result.success:
                    state = update_state(state, {"advanced_financial_output": result.data})
            except Exception as e:
                self.logger.error("Advanced Financial Modeler failed", error=str(e))
                
        return state

    async def _node_data_curator(self, state: DealState) -> DealState:
        \"\"\"Run Data Curator Agent\"\"\"
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
                    "market": state.get("market_output")
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
        \"\"\"Run Complex Reasoning Agent\"\"\"
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
        \"\"\"Run Report Architect Agent\"\"\"
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
"""
    content = content.replace(
        "    async def _node_debate", methods_to_add + "\n    async def _node_debate"
    )


# 6. Update edge methods

new_edge_method_1 = """    def _should_continue_to_advanced_financial(self, state: DealState) -> str:
        \"\"\"Determine if we should proceed to Advanced Financial Modeler\"\"\"
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
        \"\"\"Determine if we should proceed to debate\"\"\"
        if has_errors(state):
            return "error"
        return "debate"
"""
content = content.replace(
    "    def _should_continue_to_debate(self, state: DealState) -> str:\n"
    '        """Determine if we should proceed to debate"""\n'
    "        if has_errors(state):\n"
    '            return "error"\n'
    "\n"
    "        # Check if all required agents completed\n"
    '        required = ["financial_analyst", "legal_advisor", "risk_assessor"]\n'
    "        if not all_agents_completed(state, required):\n"
    '            return "wait"\n'
    "\n"
    '        return "debate"',
    new_edge_method_1.strip(),
)

content = content.replace(
    "    def _should_continue_after_halugate(self, state: DealState) -> str:\n"
    '        """After HaluGate: proceed to decision or escalate if blocked"""\n'
    "        if has_errors(state):\n"
    '            return "error"\n'
    "\n"
    '        halugate_data = state.get("context", {}).get("halugate_results", {})\n'
    '        if halugate_data.get("blocked", False):\n'
    '            self.logger.error("HaluGate BLOCKED output — escalating")\n'
    '            return "escalate"\n'
    "\n"
    '        return "decision"',
    "    def _should_continue_after_halugate(self, state: DealState) -> str:\n"
    '        """After HaluGate: proceed to report_architect or escalate if blocked"""\n'
    "        if has_errors(state):\n"
    '            return "error"\n'
    "\n"
    '        halugate_data = state.get("context", {}).get("halugate_results", {})\n'
    '        if halugate_data.get("blocked", False):\n'
    '            self.logger.error("HaluGate BLOCKED output — escalating")\n'
    '            return "escalate"\n'
    "\n"
    '        return "report_architect"',
)

with open(
    r"f:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\app\orchestrator\graph.py",
    "w",
    encoding="utf-8",
) as f:
    f.write(content)

print("graph.py patched.")
