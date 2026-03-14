"""
AI/Tech Diligence Tools for DealForge AI.

Specialized tools to assess AI/ML tech stacks, model defensibility,
and quantify AI-driven revenue uplift.
"""

from typing import Dict, Any, Optional
import structlog
from app.core.tools.tool_router import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class AIStackScannerTool(BaseTool):
    """Parses technical documents or repos to map out an AI/ML tech stack."""

    def __init__(self):
        super().__init__(
            name="ai_stack_scanner",
            description=(
                "Scans technical documents or text summaries to extract an AI/ML stack, "
                "identify dependencies, model types, and assess stack age."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "tech_summary_text": {
                    "type": "string",
                    "description": "Text body containing the target's technical documentation.",
                },
            },
            "required": ["tech_summary_text"],
        }

    async def execute(self, tech_summary_text: str = "", **kwargs) -> ToolResult:
        text = tech_summary_text.lower()

        # Simplified mock logic for identifying stack components from text
        models = []
        if "llama" in text:
            models.append("Llama")
        if "gpt" in text:
            models.append("GPT-based")
        if "pytorch" in text:
            models.append("PyTorch")
        if "tensorflow" in text:
            models.append("TensorFlow")

        infra = []
        if "aws" in text:
            infra.append("AWS")
        if "gcp" in text:
            infra.append("GCP")
        if "azure" in text:
            infra.append("Azure")

        db = []
        if "postgres" in text:
            db.append("PostgreSQL")
        if "mongo" in text:
            db.append("MongoDB")
        if "pinecone" in text or "milvus" in text or "chroma" in text:
            db.append("Vector DB")

        scorecard = {
            "models_and_frameworks": models or ["Unknown / Custom Models"],
            "infrastructure": infra or ["Unknown / On-Prem"],
            "databases": db or ["Unknown Database"],
            "has_rag_components": "rag" in text or "retrieval" in text,
            "overall_stack_age_assessment": "Modern" if models else "Legacy / Unclear",
        }

        return ToolResult(success=True, data=scorecard)


class ModelDefensibilityScorerTool(BaseTool):
    """Scores IP protection, scalability, and obsolescence risk."""

    def __init__(self):
        super().__init__(
            name="model_defensibility_scorer",
            description=(
                "Scores the target's IP protection and scalability based on stack "
                "metadata. Returns a 0-100 score and specific risk factors."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "stack_metadata": {
                    "type": "object",
                    "description": "JSON object from AIStackScannerTool containing stack details.",
                },
            },
            "required": ["stack_metadata"],
        }

    async def execute(self, stack_metadata: Dict = None, **kwargs) -> ToolResult:
        stack = stack_metadata or {}
        score = 50
        risk_factors = []

        models = stack.get("models_and_frameworks", [])

        if "PyTorch" in models or "TensorFlow" in models:
            score += 20
        else:
            risk_factors.append("No standard ML training framework detected.")

        if stack.get("has_rag_components"):
            score += 15
        else:
            risk_factors.append("No modern RAG/LLM architecture components found.")

        if "Unknown / On-Prem" in stack.get("infrastructure", []):
            risk_factors.append(
                "Scale limitations due to missing cloud infrastructure."
            )
            score -= 10
        else:
            score += 15

        if "Unknown Database" in stack.get("databases", []):
            risk_factors.append("Unclear data storage strategy.")

        # Cap score
        score = min(100, max(0, score))

        return ToolResult(
            success=True,
            data={
                "defensibility_score": score,
                "risk_factors": risk_factors,
                "assessment_level": (
                    "High" if score >= 80 else ("Medium" if score >= 50 else "Low")
                ),
            },
        )


class AIValueQuantifierTool(BaseTool):
    """Estimates AI-driven revenue uplift potential."""

    def __init__(self):
        super().__init__(
            name="ai_value_quantifier",
            description=(
                "Estimates AI-driven revenue uplift potential given current target revenue "
                "and an AI defensibility score."
            ),
        )

    def get_parameters_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "current_revenue": {
                    "type": "number",
                    "description": "Target's current baseline annual revenue.",
                },
                "defensibility_score": {
                    "type": "number",
                    "description": "Defensibility score (0-100) from ModelDefensibilityScorerTool.",
                },
            },
            "required": ["current_revenue", "defensibility_score"],
        }

    async def execute(
        self, current_revenue: float = 0.0, defensibility_score: float = 0.0, **kwargs
    ) -> ToolResult:
        if current_revenue <= 0:
            return ToolResult(success=False, data=None, error="Revenue must be > 0.")

        # Simplified uplift logic: higher score = higher % uplift potential
        base_uplift_pct = (defensibility_score / 100.0) * 0.15  # Max 15% revenue uplift

        low_uplift = current_revenue * (base_uplift_pct * 0.5)
        base_uplift = current_revenue * base_uplift_pct
        high_uplift = current_revenue * (base_uplift_pct * 1.5)

        confidence = (
            "High"
            if defensibility_score >= 80
            else ("Medium" if defensibility_score >= 50 else "Low")
        )

        estimation = {
            "low_value_uplift": round(low_uplift, 2),
            "base_value_uplift": round(base_uplift, 2),
            "high_value_uplift": round(high_uplift, 2),
            "confidence_level": confidence,
            "note": f"Estimated based on {defensibility_score}/100 defensibility score.",
        }

        return ToolResult(success=True, data=estimation)
