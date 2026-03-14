"""
Prospectus & S-1 Processing Agent — 'The Librarian'

Ingests and analyzes S-1 filings, 10-K documents, data room documents.
Extracts structured KPIs, operating metrics, and financial statements.
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class ProspectusProcessingAgent(BaseAgent):
    """
    The Librarian — processes regulatory filings and data room documents:
    - S-1 / 10-K / 10-Q filing analysis
    - KPI and operating metric extraction
    - Financial statement standardization
    - Draft-to-draft delta comparison
    """

    name = "prospectus_agent"
    description: str = "Processes S-1 filings, 10-K/10-Q documents, extracts structured KPIs and financial data"
    recommended_model: str = "Gemini 1.5 Pro (Document Extraction)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}

        try:
            # Search for relevant documents in RAG
            memory_context = []
            if self.pageindex_client:
                memory_context = await self.retrieve_context(
                    f"SEC filing S-1 10-K financial statements {task}", top_k=8
                )

            system_prompt = """You are a Senior Analyst specializing in SEC filings and prospectus review.
Your role is to extract, structure, and analyze data from regulatory documents.

EXTRACTION TARGETS:
1. Key Financial Metrics: Revenue, EBITDA, Net Income, FCF (3+ years)
2. Operating KPIs: Users, ARR, NDR, CAC, LTV, churn, margins
3. Risk Factors: Top 5 material risks with severity assessment
4. Business Model: Revenue breakdown by segment/geography
5. Management & Governance: Key executives, board composition
6. Capital Structure: Outstanding shares, options, debt instruments

OUTPUT FORMAT: Structured JSON with clear sourcing for each data point."""

            prompt = f"TASK: {task}\n\n"
            if context:
                prompt += f"CONTEXT: {json.dumps(context, default=str)[:2000]}\n\n"
            if memory_context:
                prompt += "RETRIEVED DOCUMENTS:\n"
                for i, doc in enumerate(memory_context[:5]):
                    prompt += f"[Doc {i+1}]: {str(doc)[:400]}\n"

            prompt += "\nExtract and structure all relevant financial data and KPIs."

            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")
            analysis = self._parse_output(content)

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=analysis,
                reasoning=f"Processed filing documents, extracted {len(analysis.get('kpis', {}))} KPIs.",
                confidence=0.82,
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("prospectus_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    def _parse_output(self, content: str) -> Dict:
        from app.core.json_helpers import extract_and_parse_json

        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content, "format": "narrative"}
