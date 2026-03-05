"""Database Models for DealForge AI"""

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Integer,
    JSON,
    ForeignKey,
    Text,
    Boolean,
    Enum,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
import enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


class DealStatus(str, enum.Enum):
    DRAFT = "draft"
    SCREENING = "screening"
    VALUATION = "valuation"
    DUE_DILIGENCE = "due_diligence"
    NEGOTIATION = "negotiation"
    CLOSED = "closed"
    REJECTED = "rejected"


class AgentType(str, enum.Enum):
    FINANCIAL_ANALYST = "financial_analyst"
    LEGAL_ADVISOR = "legal_advisor"
    RISK_ASSESSOR = "risk_assessor"
    MARKET_RESEARCHER = "market_researcher"
    DEBATE_MODERATOR = "debate_moderator"
    SCORING_AGENT = "scoring_agent"
    RED_TEAM = "red_team"
    # OFAS agents
    VALUATION_AGENT = "valuation_agent"
    DUE_DILIGENCE_AGENT = "due_diligence_agent"
    DCF_LBO_ARCHITECT = "dcf_lbo_architect"
    OFAS_SUPERVISOR = "ofas_supervisor"
    INVESTMENT_MEMO_AGENT = "investment_memo_agent"
    PROJECT_MANAGER = "project_manager"
    BUSINESS_ANALYST = "business_analyst"
    PROSPECTUS_AGENT = "prospectus_agent"
    TREASURY_AGENT = "treasury_agent"
    FPA_FORECASTING_AGENT = "fpa_forecasting_agent"
    TAX_COMPLIANCE_AGENT = "tax_compliance_agent"


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    WAITING = "waiting"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deals = relationship("Deal", back_populates="owner")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(Enum(DealStatus), default=DealStatus.DRAFT)

    target_company = Column(String(255))
    industry = Column(String(100))
    revenue_range = Column(String(50))
    employee_count = Column(Integer)

    asking_price = Column(Float)
    valuation_estimate = Column(Float)
    deal_score = Column(Float)
    risk_level = Column(String(20))

    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    owner = relationship("User", back_populates="deals")
    documents = relationship("Document", back_populates="deal")
    agent_runs = relationship("AgentRun", back_populates="deal")
    workflow_states = relationship("WorkflowState", back_populates="deal")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)

    filename = Column(String(255), nullable=False)
    file_path = Column(String(500))
    file_type = Column(String(50))
    file_size = Column(Integer)

    pageindex_id = Column(String(255))
    index_metadata = Column(JSON)
    summary = Column(Text)
    extracted_entities = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)

    deal = relationship("Deal", back_populates="documents")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)

    agent_type = Column(Enum(AgentType), nullable=False)
    status = Column(Enum(AgentStatus), default=AgentStatus.IDLE)

    input_data = Column(JSON)
    output_data = Column(JSON)
    reflection_score = Column(Float)
    reward = Column(Float)
    reasoning_trace = Column(JSON)

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    deal = relationship("Deal", back_populates="agent_runs")


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)

    current_node = Column(String(100))
    state_data = Column(JSON)
    execution_path = Column(JSON)
    decisions = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deal = relationship("Deal", back_populates="workflow_states")


class DealScore(Base):
    __tablename__ = "deal_scores"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False, unique=True)

    market_score = Column(Float)
    team_score = Column(Float)
    traction_score = Column(Float)
    financials_score = Column(Float)
    risk_score = Column(Float)
    strategic_fit_score = Column(Float)

    total_score = Column(Float)
    confidence = Column(Float)

    scoring_breakdown = Column(JSON)
    recommendations = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MemoryEntry(Base):
    """Shared memory for cross-agent intelligence"""

    __tablename__ = "memory_entries"

    id = Column(String(36), primary_key=True, default=gen_uuid)

    content = Column(Text, nullable=False)
    content_type = Column(String(50))
    deal_id = Column(String(36), ForeignKey("deals.id"))
    agent_type = Column(Enum(AgentType))
    tags = Column(JSON)

    pageindex_chunk_id = Column(String(255))
    relevance_score = Column(Float)
    access_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime)
