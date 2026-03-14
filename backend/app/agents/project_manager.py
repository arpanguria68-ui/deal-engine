"""
Project Manager / Scrum Master Agent — Reasoning-First Edition

3-Phase Workflow:
  Phase 1 — Data Requirements: Identify what data/files are needed. Check MCP
             for auto-fetchable items. Ask user only for what can't be self-fetched.
  Phase 2 — Clarifying Questions: Socratic questioning with visible reasoning
             before building the plan. Surface potential blockers upfront.
  Phase 3 — MECE Plan with Risk Flags: Structured task list, risks per task,
             always awaits user approval before any execution.
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput
from app.core.tasks.task_manager import get_task_manager, AGENT_CAPABILITIES

# Default task templates for common deal analysis scenarios
DEAL_ANALYSIS_TEMPLATE = [
    {
        "title": "Financial Statement Analysis",
        "description": "Analyze historical income statement, balance sheet, and cash flow for the target. Calculate key ratios (margins, leverage, coverage). Identify trends and red flags.",
        "assigned_agent": "financial_analyst",
        "priority": "critical",
    },
    {
        "title": "Company & Market Research",
        "description": "Research the target company background, industry dynamics, TAM/SAM/SOM, and competitive landscape. Identify key competitors and market trends.",
        "assigned_agent": "market_researcher",
        "priority": "high",
    },
    {
        "title": "DCF Valuation Model",
        "description": "Build a Discounted Cash Flow model for the target with 5-year projected free cash flows, WACC calculation, and terminal value. Apply mid-year convention.",
        "assigned_agent": "valuation_agent",
        "priority": "critical",
    },
    {
        "title": "Comparable Companies Analysis",
        "description": "Identify peer companies and calculate trading multiples (EV/EBITDA, EV/Revenue, P/E). Derive implied valuation range for the target.",
        "assigned_agent": "valuation_agent",
        "priority": "high",
    },
    {
        "title": "LBO Returns Analysis",
        "description": "Model leveraged buyout scenario for the target with debt waterfall, cash flow sweep, and equity returns (IRR, MOIC) at various exit multiples.",
        "assigned_agent": "dcf_lbo_architect",
        "priority": "high",
    },
    {
        "title": "Advanced Financial Modeling",
        "description": "Build rigorous 3-statement models, downside scenarios, and Monte Carlo simulations for the target.",
        "assigned_agent": "advanced_financial_modeler",
        "priority": "high",
    },
    {
        "title": "Risk Assessment & Sensitivity Analysis",
        "description": "Identify key risks for the target (market, operational, financial, regulatory). Run sensitivity analysis on critical assumptions. Build risk heatmap.",
        "assigned_agent": "risk_assessor",
        "priority": "high",
    },
    {
        "title": "Legal & Regulatory Review",
        "description": "Review legal structure, pending litigation, regulatory requirements for the target. Flag material legal risks and compliance gaps.",
        "assigned_agent": "legal_advisor",
        "priority": "medium",
    },
    {
        "title": "Commercial Due Diligence",
        "description": "Assess business model sustainability, customer concentration, revenue quality, and growth drivers for the target. Validate management projections.",
        "assigned_agent": "due_diligence_agent",
        "priority": "medium",
    },
    {
        "title": "Data Curation & Synthesis",
        "description": "Synthesize data from financial, legal, and risk agents for the target. Resolve any conflicting data points and query PageIndex for missing sector context.",
        "assigned_agent": "data_curator_agent",
        "priority": "high",
    },
    {
        "title": "Complex Reasoning & Strategy",
        "description": "Apply Chain-of-Thought reasoning to the curated data bible for the target. Formulate strategic insights and deeper transaction rationale.",
        "assigned_agent": "complex_reasoning_agent",
        "priority": "high",
    },
    {
        "title": "Bull vs Bear Debate",
        "description": "Present and debate bull case and bear case arguments for the investment in the target. Stress-test the investment thesis from both sides.",
        "assigned_agent": "debate_moderator",
        "priority": "medium",
    },
    {
        "title": "Final Scoring & Recommendation",
        "description": "Aggregate all analysis for the target into final deal score (1-10). Provide clear BUY/PASS/CONDITIONAL recommendation with key conditions.",
        "assigned_agent": "scoring_agent",
        "priority": "critical",
        "depends_on": [],
    },
    {
        "title": "Report Architecture & Theming",
        "description": "Select the appropriate report template, configure branding settings, and layout the final document structure.",
        "assigned_agent": "report_architect_agent",
        "priority": "critical",
        "depends_on": [],
    },
    {
        "title": "Investment Memo & Report Generation",
        "description": "Compile all findings into McKinsey-style investment memo with executive summary, charts (football field, risk heatmap, radar), and appendices.",
        "assigned_agent": "investment_memo_agent",
        "priority": "high",
        "depends_on": [],
    },
]

# What data types Finnhub and other MCPs can provide automatically
MCP_AUTO_FETCH_CAPABILITIES = {
    "finnhub": [
        "stock_price",
        "market_cap",
        "pe_ratio",
        "eps",
        "revenue",
        "net_income",
        "earnings_calendar",
        "company_news",
        "analyst_ratings",
        "ipo_data",
        "sector_metrics",
        "financial_statements",
    ],
    "massive": [
        "company_profile",
        "employee_count",
        "funding_history",
        "leadership_data",
        "market_research_reports",
        "alternative_data",
    ],
}

DATA_REQUIREMENTS_BY_TASK_TYPE = {
    "deal_analysis": [
        {
            "item": "Target company financial statements (3 years)",
            "source": "user_or_mcp",
            "mcp_capability": "financial_statements",
        },
        {
            "item": "Target company pitch deck / CIM",
            "source": "user_only",
            "mcp_capability": None,
        },
        {
            "item": "Term sheet or LOI (if available)",
            "source": "user_only",
            "mcp_capability": None,
        },
        {
            "item": "Stock price & market data",
            "source": "mcp_auto",
            "mcp_capability": "stock_price",
        },
        {
            "item": "Comparable company multiples",
            "source": "mcp_auto",
            "mcp_capability": "sector_metrics",
        },
        {
            "item": "Recent company news & sentiment",
            "source": "mcp_auto",
            "mcp_capability": "company_news",
        },
        {
            "item": "Analyst ratings & price targets",
            "source": "mcp_auto",
            "mcp_capability": "analyst_ratings",
        },
        {
            "item": "Management team background",
            "source": "user_or_mcp",
            "mcp_capability": "leadership_data",
        },
    ],
    "general": [
        {
            "item": "Deal overview or brief",
            "source": "user_only",
            "mcp_capability": None,
        },
        {
            "item": "Target company name & ticker (if public)",
            "source": "user_only",
            "mcp_capability": None,
        },
    ],
}


class ProjectManagerAgent(BaseAgent):
    """
    Scrum Master / Project Manager agent with 3-phase reasoning workflow:
    1. Identify data/file requirements — ask user, offer MCP auto-fetch for gaps
    2. Ask clarifying questions with visible reasoning before planning
    3. Generate MECE task plan with per-task risk flags — always await user approval
    """

    name = "project_manager"
    description: str = "Reasoning-first PM — identifies data needs, asks smart questions, creates structured task plans with risk flags before executing anything"
    recommended_model: str = "Gemini 1.5 Pro (Complex Reasoning)"

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 1 + 2 entry point
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_clarifying_questions(
        self, task: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Combined Phase 1 (data requirements) + Phase 2 (clarifying questions).
        Returns a structured response that the UI renders as an interactive checklist.
        If clarification_round >= 1, skips immediately (backend guardrail).
        """
        context = context or {}

        # ── Tier 1 Guardrail: skip if already clarified once ──
        clarification_round = context.get("clarification_round", 0)
        if clarification_round >= 1:
            return {
                "phase": "clarification",
                "clarifying_questions": [],
                "skip_reason": "Already clarified. Proceeding to planning.",
            }

        configured_mcps = context.get("available_mcp_providers", [])
        mcp_ids = [p["id"] for p in configured_mcps]

        # Determine which data requirements can be auto-fetched vs user-provided
        data_reqs = self._assess_data_requirements(task, mcp_ids)

        # Use LLM for high-quality clarifying questions if available
        if getattr(self, "llm", None):
            questions = await self._llm_clarifying_questions(task, context, data_reqs)
        else:
            questions = self._fallback_clarifying_questions(task, data_reqs)

        return {
            "phase": "clarification",
            "task_summary": task[:200],
            "data_requirements": {
                "auto_fetchable": data_reqs["auto"],
                "user_required": data_reqs["user_required"],
                "optional": data_reqs["optional"],
            },
            "mcp_note": (
                (
                    f"I have access to {len(configured_mcps)} data provider(s): "
                    + ", ".join([p["name"] for p in configured_mcps])
                    + ". I can automatically pull the auto-fetchable items above. "
                    "For user-required items, please provide them before I proceed."
                )
                if configured_mcps
                else (
                    "No MCP data providers are configured. I will need you to provide "
                    "all financial data manually, or configure Finnhub/Massive in Settings."
                )
            ),
            "clarifying_questions": questions,
            "instruction": (
                "Please answer the questions above and confirm which files/data you can provide. "
                "Then call /api/v1/scrum/plan with your answers to get the full task plan."
            ),
        }

    def _assess_data_requirements(
        self, task: str, mcp_ids: List[str]
    ) -> Dict[str, List[Dict]]:
        """Classify required data into: auto_fetchable (MCP), user_required, optional."""
        task_lower = task.lower()

        # Determine task type
        is_deal = any(
            kw in task_lower
            for kw in [
                "deal",
                "acquisition",
                "m&a",
                "invest",
                "due diligence",
                "valuation",
                "buyout",
                "lbo",
                "dcf",
                "company",
                "target",
            ]
        )
        reqs = DATA_REQUIREMENTS_BY_TASK_TYPE.get(
            "deal_analysis" if is_deal else "general"
        )

        auto = []
        user_required = []
        optional = []

        for req in reqs:
            source = req["source"]
            mcp_cap = req.get("mcp_capability")

            if source == "mcp_auto":
                # Check if any configured MCP has this capability
                can_fetch = any(
                    mcp_cap in MCP_AUTO_FETCH_CAPABILITIES.get(mid, [])
                    for mid in mcp_ids
                )
                if can_fetch:
                    auto.append(
                        {
                            "item": req["item"],
                            "fetched_by": next(
                                mid
                                for mid in mcp_ids
                                if mcp_cap in MCP_AUTO_FETCH_CAPABILITIES.get(mid, [])
                            ),
                        }
                    )
                else:
                    optional.append(
                        {
                            "item": req["item"],
                            "note": "MCP not configured — provide manually or configure a data provider in Settings",
                        }
                    )
            elif source == "user_or_mcp":
                can_fetch = mcp_cap and any(
                    mcp_cap in MCP_AUTO_FETCH_CAPABILITIES.get(mid, [])
                    for mid in mcp_ids
                )
                if can_fetch:
                    auto.append(
                        {
                            "item": req["item"],
                            "fetched_by": next(
                                mid
                                for mid in mcp_ids
                                if mcp_cap in MCP_AUTO_FETCH_CAPABILITIES.get(mid, [])
                            ),
                            "note": "Will auto-fetch; you may also provide your own version.",
                        }
                    )
                else:
                    user_required.append(
                        {
                            "item": req["item"],
                            "note": "Please provide this — MCP not configured for auto-fetch.",
                        }
                    )
            else:  # user_only
                user_required.append({"item": req["item"]})

        return {"auto": auto, "user_required": user_required, "optional": optional}

    async def _llm_clarifying_questions(
        self, task: str, context: Dict, data_reqs: Dict
    ) -> List[Dict]:
        """
        Use LLM to generate high-quality Socratic questions with reasoning.
        Injects prior memory context (Tier 2) and RL quality hints (Tier 3)
        to reduce noise and improve question selection.
        """
        from app.core.memory.clarification_memory import ClarificationMemory
        from app.core.memory.question_quality_store import QuestionQualityStore

        memory = ClarificationMemory()
        quality = QuestionQualityStore()
        deal_type = memory.detect_deal_type(task)

        # ── Tier 2: inject prior context so we don't re-ask settled questions ──
        prior_context = memory.get_context_for_prompt(deal_type, task)

        # ── Tier 3: inject historically high-quality question types ──
        quality_hints = quality.get_summary_for_prompt(deal_type)

        mcp_info = context.get("available_mcp_providers", [])
        mcp_desc = (
            ", ".join(
                [f"{p['name']} ({', '.join(p['capabilities'][:3])})" for p in mcp_info]
            )
            if mcp_info
            else "None configured"
        )

        auto_items = [r["item"] for r in data_reqs["auto"]]
        user_items = [r["item"] for r in data_reqs["user_required"]]

        prompt = f"""You are a Senior Scrum Master and Investment Banking PM. A user has asked you to help with this task:

TASK: {task}

{prior_context}{quality_hints}
CONTEXT:
- Available MCP data providers (can auto-fetch): {mcp_desc}
- Data I can auto-fetch: {json.dumps(auto_items)}
- Data user must provide: {json.dumps(user_items)}
- Agent capabilities: {list(AGENT_CAPABILITIES.keys())}

Before building a task plan, identify the 1-3 most critical unknowns that would materially change the plan design.
Do NOT ask about anything already covered in PRIOR CONTEXT above.

Return a JSON array of EXACTLY 1-3 question objects (NOT more than 3). Each must have:
- "question": The specific question to ask (1-2 sentences, crisp and focused)
- "reasoning": Why you are asking this (start with "I'm asking because...")
- "type": "data_availability" | "scope" | "constraint" | "risk" | "objective"
- "options": Optional list of 2-4 answer choices if applicable
- "potential_issue": A specific blocker this question helps surface (1 sentence)

CRITICAL: Return MAXIMUM 3 questions. Prefer 1-2 if context is already sufficient.
Return ONLY the JSON array, no other text."""

        try:
            from app.core.llm.model_router import get_model_router

            llm = get_model_router().get_client_for_agent(self.name)
            response = await llm.generate(
                prompt=prompt,
                system_prompt="You are a senior Scrum Master and investment banking PM. Return ONLY valid JSON arrays. Maximum 3 questions.",
                temperature=0.3,
            )
            content = response.get("content", "[]")
            from app.core.json_helpers import extract_and_parse_json

            questions = extract_and_parse_json(content)

            # Handle cases where local LLMs wrap the array in a dict (e.g., {"questions": [...]})
            if isinstance(questions, dict):
                for key, value in questions.items():
                    if isinstance(value, list) and len(value) > 0:
                        questions = value
                        break

            if isinstance(questions, list) and len(questions) > 0:
                # Tier 1 hard cap: never return more than 3 questions
                return questions[:3]
        except Exception as e:
            self.logger.warning("llm_clarification_failed", error=str(e))

        return self._fallback_clarifying_questions(task, data_reqs)

    def _fallback_clarifying_questions(self, task: str, data_reqs: Dict) -> List[Dict]:
        """Deterministic fallback questions when LLM is unavailable. Max 3 total."""
        questions = []

        if data_reqs["user_required"]:
            items_str = ", ".join([r["item"] for r in data_reqs["user_required"]])
            questions.append(
                {
                    "question": f"Do you have the following available to share? {items_str}",
                    "reasoning": "I'm asking because without these documents, some analytical tasks will be based on estimates rather than actuals, which significantly reduces accuracy.",
                    "type": "data_availability",
                    "options": [
                        "Yes, I have all of them",
                        "I have some — will specify below",
                        "No, please research/estimate where possible",
                    ],
                    "potential_issue": "Missing source documents may force agents to rely on public estimates, reducing the reliability of the final recommendation.",
                }
            )

        questions.extend(
            [
                {
                    "question": "What is the primary objective of this analysis? (e.g., deciding whether to proceed with a bid, benchmarking against peers, internal board presentation)",
                    "reasoning": "I'm asking because the objective determines which agents to prioritize and how deep to go on each analysis track.",
                    "type": "objective",
                    "options": [
                        "Investment decision (buy/pass)",
                        "Valuation benchmarking",
                        "Board/LP presentation",
                        "Strategic review",
                        "Other",
                    ],
                    "potential_issue": "Unclear objective leads to wasted effort on irrelevant analysis and increases turnaround time.",
                },
                {
                    "question": "What is your timeline? When do you need the completed analysis?",
                    "reasoning": "I'm asking because timeline constraints affect which tasks can be run in parallel vs. sequentially, and whether we need to skip lower-priority tasks.",
                    "type": "constraint",
                    "options": [
                        "< 24 hours (urgent)",
                        "2-3 days",
                        "1 week",
                        "No hard deadline",
                    ],
                    "potential_issue": "Tight timelines may require deprioritising deep legal/compliance review, which could expose undiscovered risks.",
                },
                {
                    "question": "Are there specific areas or risk factors you are already concerned about that you want the analysis to focus on?",
                    "reasoning": "I'm asking because known concerns should be elevated to higher-priority tasks so agents investigate them thoroughly rather than treating them as routine.",
                    "type": "risk",
                    "options": [
                        "Financial leverage/debt levels",
                        "Regulatory or compliance risk",
                        "Market competition",
                        "Key-person or management risk",
                        "Integration complexity",
                        "Other",
                    ],
                    "potential_issue": "Uninvestigated known risks are the leading cause of post-close deal regret in M&A transactions.",
                },
            ]
        )
        return questions

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 3 — Structured MECE Plan with Risk Flags
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_plan_with_risks(
        self, task: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate a MECE task plan with per-task risk flags. Never auto-executes."""
        start = datetime.utcnow()
        context = context or {}
        answers = context.get("user_answers", [])
        provided_data = context.get("provided_data", {})

        if getattr(self, "llm", None):
            tasks = await self._llm_plan(task, context)
        else:
            tasks = self._get_template_tasks(context)

        # Extract metadata for the todo list
        meta = await self._extract_deal_metadata(task, answers)
        ticker = meta.get("ticker", context.get("ticker", ""))
        company_name = meta.get(
            "company_name", context.get("company_name", "Target Company")
        )

        # Create the todo list
        deal_id = context.get("deal_id", "scratch")
        company_name = context.get("company_name", "Target Company")
        tm = get_task_manager()
        todo_list = await tm.create_todo_list(
            deal_id=deal_id,
            title=f"Deal Analysis: {company_name}",
            description=(
                f"MECE analysis pipeline for {company_name}. "
                "Review each task and its risk note before approving execution."
            ),
            items=tasks,
            ticker=ticker,
            company_name=company_name,
        )

        # Wire final tasks to depend on all prior tasks
        task_ids = [item.id for item in todo_list.items]
        for item in todo_list.items:
            if item.assigned_agent in ("scoring_agent", "investment_memo_agent"):
                item.depends_on = [tid for tid in task_ids if tid != item.id]

        elapsed = (datetime.utcnow() - start).total_seconds() * 1000

        return {
            "phase": "plan",
            "status": "awaiting_approval",
            "todo_list": todo_list.to_dict(),
            "task_count": len(todo_list.items),
            "message": (
                f"I've created {len(todo_list.items)} tasks for {company_name}. "
                "Each task includes a risk flag — please review carefully before approving. "
                "No work will start until you explicitly approve."
            ),
            "warnings": self._extract_warnings(tasks),
            "available_agents": {
                k: v["description"] for k, v in AGENT_CAPABILITIES.items()
            },
            "execution_time_ms": elapsed,
        }

    async def _llm_plan(self, task: str, context: Dict) -> List[Dict]:
        """Use LLM to build a MECE plan with per-task risk flags."""
        answers = context.get("user_answers", [])
        mcp_info = context.get("available_mcp_providers", [])
        provided_data = context.get("provided_data", {})

        prompt = f"""You are a Senior Investment Banking Project Manager.

TASK: {task}

USER ANSWERS TO CLARIFYING QUESTIONS:
{json.dumps(answers, default=str)[:2000]}

PROVIDED DATA/FILES: {json.dumps(list(provided_data.keys())) if provided_data else "None uploaded yet"}

AVAILABLE MCP PROVIDERS (auto-fetchable data):
{json.dumps([{"name": p["name"], "capabilities": p["capabilities"]} for p in mcp_info]) if mcp_info else "None configured"}

AVAILABLE AGENTS: {list(AGENT_CAPABILITIES.keys())}

Create a MECE (Mutually Exclusive, Collectively Exhaustive) task list for this analysis. Make sure to utilize specialized agents like data_curator_agent, complex_reasoning_agent, advanced_financial_modeler, and report_architect_agent.

Return a JSON array of 10-14 task objects. Each must have:
- "title": Concise task name
- "description": What this task does and the specific output it produces (2-3 sentences)
- "assigned_agent": One of the available agents listed above
- "priority": "critical" | "high" | "medium" | "low"
- "risk_flag": The most likely blocker or risk for THIS specific task (1 sentence). Be specific — not generic.
- "data_dependency": null | "requires_user_upload" | "mcp_auto_fetch" | "depends_on_prior_task"
- "mcp_source": If data_dependency is "mcp_auto_fetch", which MCP provider will fetch it. Otherwise null.

Ordering rules:
1. Data-gathering tasks first
2. Analysis tasks second (financial, market, legal, risk)
3. Synthesis tasks last (scoring, memo)

Return ONLY the JSON array, no other text."""

        try:
            from app.core.llm.model_router import get_model_router

            llm = get_model_router().get_client_for_agent(self.name)
            response = await llm.generate(
                prompt=prompt,
                system_prompt="You are a senior investment banking PM. Return only valid JSON.",
                temperature=0.3,
            )
            content = response.get("content", "[]")
            from app.core.json_helpers import extract_and_parse_json

            tasks = extract_and_parse_json(content)
            if isinstance(tasks, list) and len(tasks) > 0:
                return tasks
        except Exception as e:
            self.logger.warning("llm_plan_failed", error=str(e))

        return self._get_template_tasks(context)

    async def _extract_deal_metadata(
        self, task: str, answers: List[Dict]
    ) -> Dict[str, str]:
        """Extract ticker and company name from task or answers."""
        prompt = f"""Extract the target company name and ticker symbol (if public) from the following context:

TASK: {task}
USER ANSWERS: {json.dumps(answers)}

Return ONLY a JSON object:
{{"company_name": "...", "ticker": "..."}}

If missing, use "Target Company" and "" respectively.
"""
        try:
            from app.core.llm.model_router import get_model_router

            llm = get_model_router().get_client_for_agent(self.name)
            response = await llm.generate(prompt=prompt, temperature=0.1)
            from app.core.json_helpers import extract_and_parse_json

            return extract_and_parse_json(response.get("content", "")) or {}
        except Exception as e:
            self.logger.warning("metadata_extraction_failed", error=str(e))
            return {}

    def _extract_warnings(self, tasks: List[Dict]) -> List[str]:
        """Extract risk flags from tasks that are marked critical/high priority with blockers."""
        warnings = []
        for t in tasks:
            if t.get("risk_flag") and t.get("priority") in ("critical", "high"):
                warnings.append(f"[{t.get('title', 'Task')}] {t['risk_flag']}")
        return warnings[:5]  # Top 5 warnings

    # ─────────────────────────────────────────────────────────────────────────
    # Original run() for backward compatibility with existing orchestrator
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Create a structured todo list. Backward-compatible entrypoint."""
        start = datetime.utcnow()
        context = context or {}
        deal_id = context.get("deal_id", "unknown")
        company_name = context.get("company_name", "Target Company")

        try:
            if getattr(self, "llm", None):
                customized_tasks = await self._generate_custom_tasks(task, context)
            else:
                customized_tasks = self._get_template_tasks(context)

            tm = get_task_manager()
            todo_list = await tm.create_todo_list(
                deal_id=deal_id,
                title=f"Deal Analysis: {company_name}",
                description=(
                    f"Comprehensive deal analysis pipeline for {company_name}. "
                    "Review and edit tasks below, then approve to begin execution."
                ),
                items=customized_tasks,
            )

            task_ids = [item.id for item in todo_list.items]
            for item in todo_list.items:
                if item.assigned_agent in ("scoring_agent", "investment_memo_agent"):
                    item.depends_on = [tid for tid in task_ids if tid != item.id]

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data={
                    "todo_list": todo_list.to_dict(),
                    "message": (
                        f"Created {len(todo_list.items)} tasks for {company_name}. "
                        "Please review and approve before execution."
                    ),
                    "available_agents": {
                        k: v["description"] for k, v in AGENT_CAPABILITIES.items()
                    },
                },
                reasoning=(
                    f"Generated structured analysis pipeline with {len(todo_list.items)} tasks "
                    f"assigned to {len(set(i.assigned_agent for i in todo_list.items))} specialist agents."
                ),
                confidence=0.9,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            self.logger.error("project_manager_error", error=str(e))
            return AgentOutput(
                success=False,
                data={"error": str(e)},
                reasoning=f"Failed to create task list: {e}",
                confidence=0.0,
            )

    async def _generate_custom_tasks(self, task: str, context: Dict) -> List[Dict]:
        """Use LLM to generate customized task list based on deal specifics."""
        prompt = f"""You are a Senior Project Manager at a top-tier investment bank.
Given the following deal analysis request, create a structured task list.

DEAL REQUEST: {task}
CONTEXT: {json.dumps(context, default=str)[:2000]}

Return a JSON array of tasks. Each task object must have:
- "title": concise task name
- "description": 1-2 sentence description of what needs to be done
- "assigned_agent": one of {list(AGENT_CAPABILITIES.keys())}
- "priority": "critical" | "high" | "medium" | "low"
- "risk_flag": main risk or blocker for this task (1 sentence)

Create 10-14 tasks covering: financial modeling, data curation, complex reasoning, 
valuation, risk, market research, legal review, report architecture, and final recommendations.
Order them by logical execution sequence.

Return ONLY the JSON array, no other text."""

        try:
            from app.core.llm.model_router import get_model_router

            llm = get_model_router().get_client_for_agent(self.name)
            response = await llm.generate(
                prompt=prompt,
                system_prompt="You are a deal analysis project manager. Return only valid JSON.",
                temperature=0.3,
            )
            content = response.get("content", "[]")
            from app.core.json_helpers import extract_and_parse_json

            tasks = extract_and_parse_json(content)
            if isinstance(tasks, list) and len(tasks) > 0:
                return tasks
        except Exception as e:
            self.logger.warning("llm_task_generation_failed", error=str(e))

        return self._get_template_tasks(context)

    def _get_template_tasks(self, context: Dict) -> List[Dict]:
        """Return default template tasks with context-specific adjustments."""
        tasks = []
        for t in DEAL_ANALYSIS_TEMPLATE:
            task = {**t}
            company = context.get("company_name", "the target")
            task["description"] = task["description"].replace("the target", company)
            if "risk_flag" not in task:
                task["risk_flag"] = (
                    "Ensure all input data is available before starting this task."
                )
            tasks.append(task)
        return tasks

    # ─────────────────────────────────────────────────────────────────────────
    # Task execution (unchanged)
    # ─────────────────────────────────────────────────────────────────────────

    async def execute_task(
        self, list_id: str, task_id: str, agent_registry=None
    ) -> Dict[str, Any]:
        """Execute a single task by routing to the assigned agent."""
        tm = get_task_manager()
        todo = await tm.get_todo_list(list_id)
        if not todo:
            return {"error": f"Todo list {list_id} not found"}

        task_item = next((i for i in todo.items if i.id == task_id), None)
        if not task_item:
            return {"error": f"Task {task_id} not found"}

        await tm.update_task(list_id, task_id, {"status": "in_progress"})

        try:
            if agent_registry:
                agent = agent_registry.get(task_item.assigned_agent)
            else:
                agent = None

            if agent:
                result = await agent.run(
                    task_item.description, context={"task_id": task_id}
                )
                await tm.mark_task_result(
                    list_id,
                    task_id,
                    result.data if result.success else {"error": result.reasoning},
                )
                return result.data
            else:
                await tm.mark_task_result(
                    list_id,
                    task_id,
                    {"note": f"Agent '{task_item.assigned_agent}' not available"},
                )
                return {"note": f"Agent '{task_item.assigned_agent}' not registered"}

        except Exception as e:
            await tm.update_task(list_id, task_id, {"status": "blocked"})
            return {"error": str(e)}

    async def execute_all(self, list_id: str, agent_registry=None) -> Dict[str, Any]:
        """Execute all pending tasks in order, respecting dependencies.

        Includes Scrum Master error resilience:
        - Detects failed/blocked tasks after a full pass
        - Retries them once, optionally re-assigning to a fallback agent
        - Generates a user-facing failure summary if tasks remain incomplete
        """
        tm = get_task_manager()
        todo = await tm.get_todo_list(list_id)
        if not todo:
            return {"error": "Todo list not found"}
        if todo.status not in ("approved", "in_progress"):
            return {"error": "Todo list must be approved before execution"}

        todo.status = "in_progress"
        results = {}
        max_iterations = len(todo.items) * 2

        # ── First pass: execute all ready tasks ──
        for _ in range(max_iterations):
            ready = await tm.get_next_tasks(list_id)
            if not ready:
                break
            for task_item in ready:
                result = await self.execute_task(list_id, task_item.id, agent_registry)
                results[task_item.id] = result

        # ── Error resilience: detect and retry failed tasks ──
        todo = await tm.get_todo_list(list_id)  # Refresh from cache/DB
        failed_tasks = [
            item for item in todo.items if item.status in ("blocked", "pending")
        ]

        retried = []
        if failed_tasks:
            self.logger.warning(
                "scrum_master_retry",
                list_id=list_id,
                failed_count=len(failed_tasks),
                failed_ids=[t.id for t in failed_tasks],
            )

            for task_item in failed_tasks:
                # Reset status to pending for retry
                await tm.update_task(list_id, task_item.id, {"status": "pending"})

                # Execute retry
                retry_result = await self.execute_task(
                    list_id, task_item.id, agent_registry
                )
                results[task_item.id] = retry_result
                retried.append(task_item.id)

        # ── Final status check ──
        todo = await tm.get_todo_list(list_id)
        still_failed = [item for item in todo.items if item.status not in ("done",)]

        failure_summary = None
        if still_failed:
            failure_summary = {
                "message": f"{len(still_failed)} task(s) could not be completed after retry.",
                "failed_tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "assigned_agent": t.assigned_agent,
                        "status": t.status,
                    }
                    for t in still_failed
                ],
            }
            self.logger.error(
                "scrum_master_unresolved_failures", summary=failure_summary
            )

        return {
            "list_id": list_id,
            "status": todo.status,
            "results": results,
            "retried_tasks": retried,
            "failure_summary": failure_summary,
            "summary": todo.to_dict()["summary"],
        }
