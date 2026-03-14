"""Agents module"""

from app.agents.base import BaseAgent, AgentOutput, AgentRegistry, get_agent_registry
from app.agents.financial_analyst import FinancialAnalystAgent, ValuationAgent
from app.agents.legal_advisor import LegalAdvisorAgent, ComplianceAgent
from app.agents.risk_assessor import RiskAssessorAgent, MarketRiskAgent
from app.agents.market_researcher import (
    MarketResearcherAgent,
    DebateModeratorAgent,
    ScoringAgent,
)
from app.agents.project_manager import ProjectManagerAgent
from app.agents.dcf_lbo_architect import DCFLBOArchitectAgent
from app.agents.prospectus_agent import ProspectusProcessingAgent
from app.agents.due_diligence_agent import CommercialDueDiligenceAgent
from app.agents.investment_memo_agent import InvestmentMemoAgent
from app.agents.treasury_agent import (
    TreasuryCashAgent,
    FPAForecastingAgent,
    TaxComplianceAgent,
)
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.ofas_supervisor import OFASSupervisorAgent
from app.agents.compliance_qa_agent import ComplianceQAAgent
from app.agents.ai_tech_diligence_agent import AITechDiligenceAgent
from app.agents.esg_agent import ESGAgent
from app.agents.integration_planner_agent import IntegrationPlannerAgent
from app.agents.advanced_financial_modeler import AdvancedFinancialModelerAgent

__all__ = [
    "BaseAgent",
    "AgentOutput",
    "AgentRegistry",
    "get_agent_registry",
    # Original agents
    "FinancialAnalystAgent",
    "ValuationAgent",
    "LegalAdvisorAgent",
    "ComplianceAgent",
    "RiskAssessorAgent",
    "MarketRiskAgent",
    "MarketResearcherAgent",
    "DebateModeratorAgent",
    "ScoringAgent",
    # New agents
    "ProjectManagerAgent",
    "DCFLBOArchitectAgent",
    "ProspectusProcessingAgent",
    "CommercialDueDiligenceAgent",
    "InvestmentMemoAgent",
    "TreasuryCashAgent",
    "FPAForecastingAgent",
    "TaxComplianceAgent",
    "BusinessAnalystAgent",
    "OFASSupervisorAgent",
    "ComplianceQAAgent",
    "AITechDiligenceAgent",
    "ESGAgent",
    "IntegrationPlannerAgent",
    "AdvancedFinancialModelerAgent",
]
