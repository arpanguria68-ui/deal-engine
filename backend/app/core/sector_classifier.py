import os
import structlog
from typing import Optional
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.providers.provider_factory import get_provider

logger = structlog.get_logger(__name__)


def classify_sector(company_name: str, company_description: str) -> str:
    """
    Uses LLM to dynamically classify a company into a supported sector adapter.
    """
    sectors_dir = os.path.join(os.path.dirname(__file__), "sector_adapters")
    supported = []
    if os.path.exists(sectors_dir):
        supported = [
            f.replace(".yaml", "")
            for f in os.listdir(sectors_dir)
            if f.endswith(".yaml")
        ]

    if not supported:
        return "general"

    prompt = f"""
    You are an expert M&A Sector Classifier for DealForge AI.
    Classify the following company into ONE of the supported sectors based on its profile.
    
    Company: {company_name}
    Context/Description: {company_description}
    
    Supported Sectors: {', '.join(supported)}
    
    Respond with ONLY the exact string of the matching sector from the list above. 
    If none match well, respond with 'general'.
    """

    try:
        provider = get_provider()
        llm = provider.get_model()
        messages = [
            SystemMessage(
                content="You classify companies into specific industry sectors based on available adapters."
            ),
            HumanMessage(content=prompt),
        ]
        resp = llm.invoke(messages)
        res_text = resp.content.strip().lower()

        for s in supported:
            if s in res_text:
                logger.info("sector_classified", company=company_name, sector=s)
                return s
        logger.info("sector_fallback_general", company=company_name, result=res_text)
        return "general"
    except Exception as e:
        logger.error("sector_classification_error", error=str(e))
        return "general"
