"""
Commercial Due Diligence Agent — 'The Strategist' (OFAS Enhanced)

Analyzes CIMs, identifies market peers, screens deals against investment thesis.

OFAS Enhancements:
- Auto-injects RAG context with chunk_id tracking for citation trails
- Stores key findings to MemoryEntry for cross-deal intelligence
- Synergy analysis with source attribution
"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class CommercialDueDiligenceAgent(BaseAgent):
    """
    The Strategist — commercial due diligence:
    - CIM analysis and deal screening
    - Dynamic peer identification (beyond GICS)
    - Investment thesis validation
    - Revenue quality and growth driver assessment
    - Synergy analysis with RAG citation trails (OFAS)
    """

    name = "due_diligence_agent"
    description = "Commercial due diligence — CIM analysis, peer identification, thesis validation, synergy analysis"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        start = datetime.utcnow()
        context = context or {}
        action = context.get("action", "full_dd")

        try:
            # Route to specific analysis if requested
            if action == "synergy_analysis":
                return await self._run_synergy_analysis(task, context, start)

            # ── Auto-RAG context injection with chunk tracking ──
            memory_context = []
            rag_citations = []  # Track chunk_ids for citation trail

            if self.memory:
                chunks = await self.retrieve_context(
                    f"due diligence CIM peer analysis {task}", top_k=8
                )
                for chunk in chunks:
                    if isinstance(chunk, dict):
                        memory_context.append(chunk)
                        if chunk.get("chunk_id") or chunk.get("id"):
                            rag_citations.append(
                                {
                                    "chunk_id": chunk.get("chunk_id")
                                    or chunk.get("id"),
                                    "content_preview": str(chunk.get("content", ""))[
                                        :150
                                    ],
                                    "score": chunk.get("relevance_score")
                                    or chunk.get("score", 0),
                                    "page": chunk.get("page_number"),
                                    "source": chunk.get(
                                        "source_file", "uploaded_document"
                                    ),
                                }
                            )
                    else:
                        memory_context.append({"content": str(chunk)})

            # ── Cross-deal intelligence from MemoryEntry ──
            cross_deal_context = await self._get_cross_deal_context(context)

            system_prompt = """You are a Senior Strategy Consultant at McKinsey/Bain performing commercial due diligence.

ANALYSIS FRAMEWORK:
1. Business Model Assessment
   - Revenue model (recurring vs transactional)
   - Customer concentration risk
   - Revenue quality (organic vs acquired)
   - Unit economics (CAC, LTV, payback)

2. Market & Competitive Position
   - TAM/SAM/SOM sizing
   - Competitive moat analysis (Porter's Five Forces)
   - Dynamic peer identification (news co-mentions, business model similarity)
   - Market share trajectory

3. Growth Driver Validation
   - Historical growth decomposition (volume vs price vs mix)
   - Management projection reasonableness
   - Organic vs inorganic growth split
   - End-market growth vs company growth delta

4. Deal Thesis Screening
   - Does the target match the fund's thesis?
   - Key thesis risks and mitigants
   - Value creation levers (revenue, margin, multiple)

5. Risk Assessment
   - Customer concentration (Herfindahl index if data available)
   - Technology obsolescence risk
   - Regulatory and compliance risks
   - Key person dependency

CITATION RULE: When referencing specific data or facts from the provided documents,
note the source by referencing the document chunk or page number.

OUTPUT: Respond with structured JSON containing your assessment and source_citations."""

            # Build prompt with RAG context and cross-deal intelligence
            prompt = f"TASK: {task}\n\n"
            if context:
                safe_ctx = {k: v for k, v in context.items() if k != "action"}
                prompt += f"CONTEXT: {json.dumps(safe_ctx, default=str)[:2000]}\n\n"

            if memory_context:
                prompt += "RELEVANT DOCUMENTS (cite these when referencing data):\n"
                for i, doc in enumerate(memory_context[:5]):
                    content = str(doc.get("content", doc))[:400]
                    chunk_id = doc.get("chunk_id") or doc.get("id", f"doc_{i}")
                    prompt += f"[DOC-{i+1} | chunk:{chunk_id}] {content}\n\n"

            if cross_deal_context:
                prompt += "CROSS-DEAL INTELLIGENCE (patterns from prior analyses):\n"
                for insight in cross_deal_context[:3]:
                    prompt += f"- [{insight.get('agent_type', 'unknown')}] {insight.get('content', '')[:200]}\n"
                prompt += "\n"

            prompt += """Respond with JSON:
{
    "business_model": {"revenue_type": "...", "unit_economics": {}, "quality_score": 0},
    "market_position": {"tam": "...", "competitive_moat": "...", "market_share_trend": "..."},
    "growth_drivers": {"historical_cagr": "...", "projection_assessment": "...", "key_drivers": []},
    "deal_thesis": {"alignment": "strong|moderate|weak", "value_creation_levers": [], "key_risks": []},
    "risk_matrix": [{"risk": "...", "severity": "high|medium|low", "likelihood": "high|medium|low", "mitigant": "..."}],
    "recommendation": "proceed|caution|reject",
    "confidence_score": 0.8,
    "source_citations": [{"finding": "...", "source": "chunk_id or doc reference"}],
    "reasoning": "..."
}"""

            result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
            content = result.get("content", "")
            analysis = self._parse_output(content)

            # ── Inject RAG citations into output ──
            if rag_citations:
                analysis["_rag_context"] = {
                    "chunks_used": len(rag_citations),
                    "citations": rag_citations,
                }

            # ── Auto-store key findings to MemoryEntry ──
            await self._store_findings(analysis, context)

            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentOutput(
                success=True,
                data=analysis,
                reasoning=analysis.get(
                    "reasoning", "Completed commercial due diligence assessment."
                ),
                confidence=analysis.get("confidence_score", 0.80),
                execution_time_ms=elapsed,
                tool_calls=result.get("tool_calls"),
            )

        except Exception as e:
            self.logger.error("due_diligence_error", error=str(e))
            return AgentOutput(
                success=False, data={"error": str(e)}, reasoning=str(e), confidence=0.0
            )

    async def _run_synergy_analysis(
        self, task: str, context: Dict, start: datetime
    ) -> AgentOutput:
        """
        Synergy analysis between acquirer and target.
        Links findings to RAG chunk_ids for audit trail.
        """
        acquirer = context.get("acquirer", "Acquirer")
        target = context.get("target", "Target")

        # Get RAG context for both companies
        rag_citations = []
        combined_context = []

        if self.memory:
            for query in [
                f"{acquirer} revenue operations market share",
                f"{target} revenue operations financials",
                f"synergies cost savings revenue enhancement",
            ]:
                chunks = await self.retrieve_context(query, top_k=3)
                for chunk in chunks:
                    if isinstance(chunk, dict):
                        combined_context.append(chunk)
                        rag_citations.append(
                            {
                                "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
                                "query": query,
                                "score": chunk.get("score", 0),
                            }
                        )

        system_prompt = f"""You are a Senior M&A Consultant performing synergy analysis
for the acquisition of {target} by {acquirer}.

SYNERGY FRAMEWORK:
1. Revenue Synergies — cross-sell, geo expansion, bundling
2. Cost Synergies — overhead, procurement, IT, real estate
3. Strategic Synergies — IP, market position, talent, licensing
4. Integration Risks — culture, retention, customer churn, systems

CITATION RULE: Reference source document chunk IDs when citing specific data.
OUTPUT structured JSON."""

        prompt = f"TASK: {task}\n\n"
        if combined_context:
            prompt += "SOURCE DOCUMENTS:\n"
            for i, doc in enumerate(combined_context[:6]):
                chunk_id = doc.get("chunk_id") or doc.get("id", f"doc_{i}")
                content = str(doc.get("content", ""))[:300]
                prompt += f"[CHUNK-{chunk_id}] {content}\n\n"

        prompt += """Respond with JSON:
{
    "revenue_synergies": [{"type": "...", "estimated_value": "...", "confidence": "high|medium|low", "source_chunk": "..."}],
    "cost_synergies": [{"type": "...", "estimated_value": "...", "confidence": "high|medium|low", "source_chunk": "..."}],
    "strategic_synergies": [],
    "integration_risks": [{"risk": "...", "severity": "...", "mitigant": "..."}],
    "total_synergy_estimate": {"low": 0, "mid": 0, "high": 0},
    "realization_timeline_months": 24,
    "source_citations": [{"finding": "...", "chunk_id": "..."}],
    "reasoning": "..."
}"""

        result = await self.generate_with_tools(prompt, system_prompt=system_prompt)
        analysis = self._parse_output(result.get("content", ""))

        analysis["_rag_context"] = {
            "chunks_used": len(rag_citations),
            "citations": rag_citations,
        }

        await self._store_findings(analysis, context, finding_type="synergy_analysis")

        elapsed = (datetime.utcnow() - start).total_seconds() * 1000
        return AgentOutput(
            success=True,
            data=analysis,
            reasoning=analysis.get(
                "reasoning", f"Synergy analysis for {acquirer} + {target} complete."
            ),
            confidence=0.75,
            execution_time_ms=elapsed,
        )

    async def _get_cross_deal_context(self, context: Dict) -> List[Dict]:
        """Fetch relevant insights from previous deals via MemoryEntry"""
        try:
            from app.core.memory.memory_service import get_memory_service

            svc = get_memory_service()
            return await svc.read_memory(
                agent_type="due_diligence_agent",
                limit=5,
                min_relevance=0.5,
            )
        except Exception:
            return []

    async def _store_findings(
        self, analysis: Dict, context: Dict, finding_type: str = "dd_assessment"
    ):
        """Auto-store key findings to MemoryEntry for future cross-deal use"""
        try:
            from app.core.memory.memory_service import get_memory_service

            svc = get_memory_service()

            deal_id = context.get("deal_id")
            recommendation = analysis.get("recommendation", "")
            reasoning = analysis.get("reasoning", "")[:500]

            risks = analysis.get("risk_matrix", analysis.get("integration_risks", []))
            risk_summary = "; ".join(
                r.get("risk", "") for r in risks[:3] if isinstance(r, dict)
            )

            content = (
                f"[{finding_type.upper()}] Recommendation: {recommendation}. "
                f"Key risks: {risk_summary or 'None identified'}. "
                f"Reasoning: {reasoning}"
            )

            tags = [finding_type]
            if analysis.get("recommendation") == "reject":
                tags.append("rejected_deal")
            if risk_summary:
                tags.append("has_risks")

            chunk_id = None
            rag_ctx = analysis.get("_rag_context", {})
            if rag_ctx.get("citations"):
                chunk_id = rag_ctx["citations"][0].get("chunk_id")

            await svc.write_memory(
                content=content,
                deal_id=deal_id,
                agent_type="due_diligence_agent",
                tags=tags,
                chunk_id=chunk_id,
                relevance_score=analysis.get("confidence_score", 0.7),
            )

        except Exception as e:
            self.logger.warning("Failed to store DD findings", error=str(e))

    def _parse_output(self, content: str) -> Dict:
        from app.core.json_helpers import extract_and_parse_json

        parsed = extract_and_parse_json(content)
        if parsed:
            return parsed
        return {"analysis": content}
