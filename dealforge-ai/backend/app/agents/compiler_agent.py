"""Report Compiler Agent"""

from typing import Dict, Any, Optional
import json
import base64
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class ReportCompilerAgent(BaseAgent):
    """
    Coordinates and executes the compilation of final deal reports.

    Responsibilities:
    - Assess all completed agent tasks
    - Extract synthesis and key metrics
    - Generate standard McKinsey-styled deliverables (PPTX, PDF, Excel)
    """

    name = "compiler_agent"
    description: str = (
        "Compiles all deal analysis into final deliverables (PPTX, PDF, Excel)."
    )
    recommended_model: str = "Mistral Large 2 or Gemini 1.5 Pro (High-Fidelity Synthesis)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Execute report compilation task"""
        start_time = datetime.now()
        self.logger.info("Starting report compilation", task=task)

        # Context contains the full deal state, including other agents' results
        deal_state = context.get("deal_state", {})
        target_formats = context.get("formats", ["pptx", "pdf", "excel"])

        # Determine dynamic truncation limit based on the LLM's context window
        max_ctx = getattr(self.llm, "max_context", 12000)
        if max_ctx >= 100000:
            trunc_limit = 100000  # High-context (Gemini)
        elif max_ctx >= 30000:
            trunc_limit = 15000   # Mid-context (Mistral/GPT-4)
        else:
            trunc_limit = 4000    # Low-context (Local/Ollama)

        self.logger.info("Dynamic context scaling applied", 
                         provider=getattr(self.llm, "provider", "unknown"),
                         max_context=max_ctx, 
                         trunc_limit=trunc_limit)

        # Truncate agent results to prevent context overflow
        agent_results = context.get("agent_results", [])
        for res in agent_results:
            if "reasoning" in res and isinstance(res["reasoning"], str):
                if len(res["reasoning"]) > trunc_limit:
                    res["reasoning"] = res["reasoning"][:trunc_limit] + f"... [TRUNCATED at {trunc_limit} chars]"

        # Build synthesis prompt
        prompt = self._build_compilation_prompt(task, deal_state, target_formats, agent_results)
        system_prompt = self._build_system_prompt()

        # The LLM will decide how to structure the narrative and call the `generate_report` tool
        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            # Parse the LLM's structural narrative decisions
            from app.core.json_helpers import extract_and_parse_json

            narrative_data = extract_and_parse_json(response["content"])

            # Extract generated files from the tool context (handled natively by base.py execute loop)
            generated_files = {}
            if "tool_results" in response:
                for res in response["tool_results"]:
                    if res.get("name") == "generate_report":
                        output = res.get("result", {})
                        if output.get("success"):
                            data = output.get("data", {})
                            ext = data.get("file_extension")
                            if ext:
                                generated_files[ext] = data.get("file_bytes_base64")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data={
                    "narrative_structure": narrative_data,
                    "generated_formats": list(generated_files.keys()),
                    "files_base64": generated_files,
                },
                reasoning=narrative_data.get(
                    "reasoning", "Compiled requested reports."
                ),
                confidence=1.0 if generated_files else 0.0,
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Report compilation failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Compilation failed: {str(e)}",
                confidence=0.0,
            )

    def _build_compilation_prompt(
        self, task: str, deal_state: Dict, formats: list, agent_results: list
    ) -> str:
        """Build the instruction set for the compiler LLM"""
        agents_run = deal_state.get("agents_run", [])
        deal_info = {
            "name": deal_state.get("deal_name", "Unknown Deal"),
            "target": deal_state.get("target_company", "Unknown Target"),
            "score": deal_state.get("final_score", 0),
            "agents_completed": agents_run,
        }

        return f"""Task: {task}

Requested Formats: {formats}
Deal Context Summary: {json.dumps(deal_info, indent=2)}

--- AGENT ANALYSIS RESULTS ---
{json.dumps(agent_results, indent=2)}

You must generate the requested reports by calling the `generate_report` tool for EACH format requested.
The available tool is: `generate_report(format: str, deal_context: dict, analyst_data: dict, agent_results: list)`.

Steps:
1. Analyze the deal context and agent results provided.
2. Synthesize a core narrative (Executive Summary, Financial Synthesis, Key Takeaways).
3. call `generate_report` once for each format in {formats}.
4. Provide your final narrative synthesis in the JSON format below.

Pass the core deal context, your synthesized `analyst_data`, and the full `agent_results` to the `generate_report` tool.

Respond with structured JSON detailing your narrative synthesis:
{{
    "executive_summary": {{
        "situation": "string",
        "complication": "string",
        "question": "string",
        "answer": "string"
    }},
    "financial_synthesis": {{
        "narrative": "string"
    }},
    "key_takeaways": [
        {{"title": "string", "description": "string"}}
    ],
    "action_items": ["string"],
    "reasoning": "string"
}}"""

    def _build_system_prompt(self) -> str:
        """Build system prompt for the compiler"""
        return f"""You are {self.name}, {self.description}.
You are a Senior Publishing Director at a top-tier management consulting firm.

CRITICAL RULES:
1. You MUST call the `generate_report` tool to create the files.
2. If multiple formats are requested, call the tool multiple times (one for each format).
3. Do NOT hallucinate tool names. Only use `generate_report`.
4. Your final output must be PURE JSON matching the requested schema.
"""
