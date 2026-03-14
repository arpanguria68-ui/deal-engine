"""Legal Advisor Agent"""

from typing import Dict, Any, Optional, List
import json
from datetime import datetime

from app.agents.base import BaseAgent, AgentOutput


class LegalAdvisorAgent(BaseAgent):
    """
    Agent for legal analysis and due diligence

    Responsibilities:
    - Contract review
    - Legal risk identification
    - Compliance assessment
    - IP analysis
    - Litigation check
    """

    name = "legal_advisor"
    description: str = "Analyzes legal documents and identifies legal risks"
    recommended_model: str = "Gemini 1.5 Pro (Contract Analysis)"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """
        Execute legal analysis task

        Args:
            task: Legal analysis task
            context: Deal context with legal documents

        Returns:
            AgentOutput with legal analysis
        """
        start_time = datetime.now()
        self.logger.info("Starting legal analysis", task=task)

        deal_id = context.get("deal_id") if context else None

        # Retrieve legal documents
        legal_docs = []
        if deal_id:
            legal_docs = await self.retrieve_context(
                f"legal contract agreement terms liability {deal_id}", top_k=8
            )

        # Build analysis prompt
        prompt = self._build_analysis_prompt(task, context, legal_docs)

        # RL Loop: Inject historically successful patterns
        from app.core.quality.agent_quality_store import AgentQualityStore

        quality_store = AgentQualityStore()
        await quality_store.initialize()
        best_practices = await quality_store.get_historical_best_practices(
            self.name, "deal_analysis"
        )

        system_prompt = self._build_system_prompt(best_practices)

        # Generate analysis
        response = await self.generate_with_tools(prompt, system_prompt)

        try:
            analysis_data = self._parse_analysis_output(response["content"])

            # Use legal clause tool for specific clauses
            if context and context.get("clauses"):
                clause_analyses = []
                for clause in context["clauses"]:
                    tool_result = await self.tools.execute(
                        "legal_clause_analyzer",
                        {"clause_text": clause["text"], "clause_type": clause["type"]},
                    )
                    if tool_result.success:
                        clause_analyses.append(tool_result.data)

                analysis_data["clause_analyses"] = clause_analyses

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return AgentOutput(
                success=True,
                data=analysis_data,
                reasoning=analysis_data.get("reasoning", ""),
                confidence=self._calculate_confidence(analysis_data),
                execution_time_ms=execution_time,
                tool_calls=response.get("function_calls"),
            )

        except Exception as e:
            self.logger.error("Legal analysis failed", error=str(e))
            return AgentOutput(
                success=False,
                data={},
                reasoning=f"Analysis failed: {str(e)}",
                confidence=0.0,
            )

    def _build_analysis_prompt(
        self, task: str, context: Optional[Dict], legal_docs: list
    ) -> str:
        """Build legal analysis prompt"""
        context_str = (
            json.dumps(context, indent=2) if context else "No additional context"
        )
        docs_str = (
            "\n".join([f"- {d['content'][:300]}..." for d in legal_docs])
            if legal_docs
            else "No legal documents retrieved"
        )

        return f"""Task: {task}

Context:
{context_str}

Legal Documents:
{docs_str}

Provide comprehensive legal analysis:
1. Corporate structure and governance
2. Material contracts review
3. Intellectual property assessment
4. Litigation and disputes
5. Regulatory compliance
6. Employment and labor issues
7. Environmental liabilities
8. Key legal risks and recommendations

Respond with structured JSON:
{{
    "corporate_structure": {{
        "entity_type": string,
        "jurisdiction": string,
        "ownership_structure": string,
        "concerns": [string]
    }},
    "material_contracts": [{{
        "contract_type": string,
        "key_terms": string,
        "risks": [string]
    }}],
    "intellectual_property": {{
        "patents": number,
        "trademarks": number,
        "ip_risks": [string]
    }},
    "litigation": {{
        "pending_cases": [string],
        "potential_exposure": string
    }},
    "regulatory_compliance": {{
        "applicable_regulations": [string],
        "compliance_status": string,
        "gaps": [string]
    }},
    "key_legal_risks": [string],
    "recommendations": [string],
    "overall_legal_risk": "low" | "medium" | "high" | "critical",
    "reasoning": string
}}"""

    def _build_system_prompt(self, best_practices: List[str] = None) -> str:
        """Build system prompt for legal analysis"""
        prompt = f"""You are {self.name}, {self.description}.

You are a senior M&A attorney with expertise in:
- Corporate law and governance
- Contract review and negotiation
- Intellectual property
- Regulatory compliance
- Litigation risk assessment
- Due diligence

Guidelines:
- **CRITICAL: NEVER hallucinate clauses, legal risks, or regulatory data. You must use your provided tools to fetch real data.**
- Use `sec_filings` or `document_search` to review actual contract language.
- Identify all material legal risks based on retrieved documents.
- Assess probability and impact of each risk.
- Recommend specific mitigation strategies.
- Flag deal-breaker issues.
- Cite specific contract language and tool source when relevant.
- Distinguish between standard and unusual terms.
"""
        if best_practices:
            prompt += (
                "\n\nHistorical Best Practices (Learn from past high-scoring deals):\n"
            )
            for bp in best_practices:
                prompt += f"- {bp}\n"

        return prompt

    def _parse_analysis_output(self, content: str) -> Dict[str, Any]:
        """Parse legal analysis output"""
        from app.core.json_helpers import extract_and_parse_json

        return extract_and_parse_json(content)

    def _calculate_confidence(self, analysis_data: Dict) -> float:
        """Calculate confidence score"""
        confidence = 0.5

        if analysis_data.get("material_contracts"):
            confidence += 0.2

        if analysis_data.get("key_legal_risks"):
            confidence += 0.15

        if analysis_data.get("reasoning") and len(analysis_data["reasoning"]) > 100:
            confidence += 0.15

        return min(1.0, confidence)

    async def analyze_contract(
        self, contract_text: str, contract_type: str
    ) -> Dict[str, Any]:
        """Analyze a specific contract"""
        prompt = f"""Analyze this {contract_type} contract:

{contract_text[:5000]}

Identify:
1. Key terms and obligations
2. Unusual or non-standard provisions
3. Potential risks and liabilities
4. Missing standard protections
5. Recommendations for negotiation"""

        response = await self.llm.generate(prompt, self._build_system_prompt())

        return {"contract_type": contract_type, "analysis": response["content"]}

    async def check_compliance(
        self, business_description: str, jurisdictions: List[str]
    ) -> Dict[str, Any]:
        """Check regulatory compliance requirements"""
        prompt = f"""Assess regulatory compliance for:

Business: {business_description}
Jurisdictions: {', '.join(jurisdictions)}

Identify:
1. Applicable regulations
2. Compliance requirements
3. Potential gaps
4. Remediation recommendations"""

        response = await self.llm.generate(prompt, self._build_system_prompt())

        return {
            "jurisdictions": jurisdictions,
            "compliance_analysis": response["content"],
        }


class ComplianceAgent(BaseAgent):
    """Specialized agent for regulatory compliance"""

    name = "compliance_agent"
    description = "Specializes in regulatory compliance assessment"

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentOutput:
        """Execute compliance assessment"""
        start_time = datetime.now()

        industry = context.get("industry", "technology") if context else "technology"
        jurisdictions = context.get("jurisdictions", ["US"]) if context else ["US"]

        # Build compliance checklist
        checklist = self._build_compliance_checklist(industry, jurisdictions)

        # Assess each item
        assessment_results = []
        for item in checklist:
            result = await self._assess_compliance_item(item, context)
            assessment_results.append(result)

        # Calculate overall compliance score
        compliant_count = sum(
            1 for r in assessment_results if r["status"] == "compliant"
        )
        compliance_score = (
            compliant_count / len(assessment_results) if assessment_results else 0
        )

        execution_time = (datetime.now() - start_time).total_seconds() * 1000

        return AgentOutput(
            success=True,
            data={
                "compliance_score": compliance_score,
                "assessment_results": assessment_results,
                "gaps": [r for r in assessment_results if r["status"] != "compliant"],
                "industry": industry,
                "jurisdictions": jurisdictions,
            },
            reasoning=f"Compliance assessment across {len(jurisdictions)} jurisdictions",
            confidence=0.7,
            execution_time_ms=execution_time,
        )

    def _build_compliance_checklist(
        self, industry: str, jurisdictions: List[str]
    ) -> List[Dict]:
        """Build industry-specific compliance checklist"""
        base_items = [
            {"category": "Corporate", "requirement": "Entity registration"},
            {"category": "Corporate", "requirement": "Annual filings"},
            {"category": "Tax", "requirement": "Tax compliance"},
            {"category": "Employment", "requirement": "Labor law compliance"},
            {"category": "Data", "requirement": "Data protection"},
        ]

        # Add industry-specific items
        if industry.lower() in ["healthcare", "medical"]:
            base_items.extend(
                [
                    {"category": "Healthcare", "requirement": "HIPAA compliance"},
                    {"category": "Healthcare", "requirement": "FDA regulations"},
                ]
            )
        elif industry.lower() in ["fintech", "financial"]:
            base_items.extend(
                [
                    {"category": "Financial", "requirement": "Banking regulations"},
                    {"category": "Financial", "requirement": "Anti-money laundering"},
                ]
            )

        return base_items

    async def _assess_compliance_item(
        self, item: Dict, context: Optional[Dict]
    ) -> Dict:
        """Assess a single compliance item"""
        # This would check actual compliance in production
        # For now, return placeholder
        return {
            "category": item["category"],
            "requirement": item["requirement"],
            "status": "unknown",  # compliant, non_compliant, partial, unknown
            "evidence": None,
            "remediation": None,
        }
