import platform

platform.system = lambda: "Windows"
platform.release = lambda: "10"
platform.version = lambda: "10.0.19045"
platform.machine = lambda: "AMD64"
platform.architecture = lambda *a, **kw: ("64bit", "WindowsPE")

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uuid
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from app.config import get_settings
from app.db.session import init_db, close_db, get_db, AsyncSessionLocal
from app.orchestrator.state import DealState, DealStage
from app.core.memory.pageindex_client import get_pageindex_client
from app.agents.base import get_agent_registry
from app.core.scoring.deal_scorer import DealScorer, risk_label
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

from app.core.redis_store import RedisStore


@asynccontextmanager
async def async_lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("Starting DealForge AI")
    await init_db()

    # Load previously saved settings
    from app.core.settings_service import SettingsService

    svc = SettingsService.get_instance()
    svc._apply_to_system()
    logger.info("Runtime settings loaded from disk")

    # Initialize Redis Store
    RedisStore.get_instance()

    yield

    # Shutdown
    logger.info("Shutting down DealForge AI")
    await close_db()
    await RedisStore.get_instance().close()


def get_orchestrator_instance():
    """Lazily import and initialize the orchestrator"""
    from app.orchestrator.graph import get_orchestrator

    return get_orchestrator()


# Create FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-Agent M&A Simulation Platform",
    lifespan=async_lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Security
security = HTTPBearer()


# ===== Pydantic Models for API =====

from pydantic import BaseModel, Field


class DealCreateRequest(BaseModel):
    """Request to create a new deal"""

    name: str = Field(..., description="Deal name")
    description: Optional[str] = None
    target_company: str
    industry: Optional[str] = "technology"
    context: Optional[dict] = {}


class DealResponse(BaseModel):
    """Deal response model"""

    id: str
    name: str
    status: str
    target_company: str
    current_stage: str
    final_score: Optional[float] = None
    final_recommendation: Optional[str] = None
    created_at: str


class AgentRunRequest(BaseModel):
    """Request to run a specific agent"""

    agent_type: str
    task: str
    context: Optional[dict] = {}


class AgentRunResponse(BaseModel):
    """Agent run response"""

    agent_type: str
    success: bool
    data: dict
    reasoning: str
    confidence: float
    provider: Optional[str] = None
    execution_time_ms: Optional[float] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""

    document_id: str
    filename: str
    pageindex_id: Optional[str] = None
    status: str


class DocumentQueryRequest(BaseModel):
    """Request to query documentation"""

    query: str
    deal_id: Optional[str] = None


class DealScoreResponse(BaseModel):
    """Deal scoring response"""

    total_score: float
    risk_level: str
    components: List[dict]
    recommendations: List[str]
    red_flags: List[str]
    green_flags: List[str]


# ===== API Routes =====


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
    }


@app.get("/api/health")
@app.get("/api/v1/health")
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ===== Deal Management Routes =====


@app.post("/api/v1/deals", response_model=DealResponse)
async def create_deal(request: DealCreateRequest):
    """Create a new deal and persist it in the in-memory store"""
    deal_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    logger.info(
        "Creating new deal",
        deal_id=deal_id,
        name=request.name,
        target=request.target_company,
    )

    deal = {
        "id": deal_id,
        "name": request.name,
        "status": "created",
        "target_company": request.target_company,
        "industry": request.industry or "technology",
        "current_stage": "init",
        "final_score": None,
        "final_recommendation": None,
        "agents_run": [],
        "created_at": now,
        "updated_at": now,
    }
    redis_store = RedisStore.get_instance()
    await redis_store.save_deal(deal_id, deal)

    return DealResponse(
        id=deal_id,
        name=request.name,
        status="created",
        target_company=request.target_company,
        current_stage="init",
        created_at=now,
    )


@app.get("/api/v1/deals")
async def list_deals():
    """List all deals from the Redis store"""
    redis_store = RedisStore.get_instance()
    deals = await redis_store.list_deals()
    return {"deals": deals}


async def update_deal(deal_id: str, request: Request):
    """Update a deal's status, stage, score, or recommendation."""
    redis_store = RedisStore.get_instance()
    deal = await redis_store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    body = await request.json()

    for key in ("status", "current_stage", "final_score", "final_recommendation"):
        if key in body:
            deal[key] = body[key]

    deal["updated_at"] = datetime.utcnow().isoformat()
    await redis_store.save_deal(deal_id, deal)
    logger.info("deal_updated", deal_id=deal_id, updates=list(body.keys()))
    return deal


@app.get("/api/v1/deals/{deal_id}/provenance")
async def get_deal_provenance(
    deal_id: str, agent_name: Optional[str] = None, tool_name: Optional[str] = None
):
    """Get provenance records for a deal's tool executions"""
    from app.core.provenance import get_provenance_collector

    records = await get_provenance_collector().get_records(
        deal_id=deal_id, agent_name=agent_name, tool_name=tool_name
    )
    return {"records": records}


@app.get("/api/v1/deals/{deal_id}/provenance/export")
async def export_deal_provenance(deal_id: str):
    """Export full provenance chain for a deal"""
    from app.core.provenance import get_provenance_collector

    export_data = await get_provenance_collector().export_chain(deal_id)
    return export_data


@app.get("/api/v1/dashboard/metrics")
async def dashboard_metrics():
    """Return live dashboard KPIs and agent activity feed"""
    redis_store = RedisStore.get_instance()
    deals = await redis_store.list_deals()
    agent_activity = await redis_store.get_global_activity()

    total = len(deals)
    scores = [d["final_score"] for d in deals if d.get("final_score") is not None]
    avg_score = round(sum(scores) / len(scores) * 100, 1) if scores else 0
    high_risk = sum(
        1 for d in deals if d.get("final_score") is not None and d["final_score"] < 0.5
    )
    active = sum(1 for d in deals if d["status"] in ("created", "running"))
    completed = sum(1 for d in deals if d["status"] == "completed")

    return {
        "total_deals": total,
        "active_deals": active,
        "completed_deals": completed,
        "avg_confidence": avg_score,
        "high_risk_alerts": high_risk,
        "deals": deals,
        "agent_activity": agent_activity[-20:],  # last 20 events
    }


@app.post("/api/v1/agent-activity")
async def log_agent_activity(event: dict):
    """Log an agent completion event and auto-complete deals when all agents have run"""
    event.setdefault("timestamp", datetime.utcnow().isoformat())

    redis_store = RedisStore.get_instance()
    await redis_store.add_activity(event)

    deal_id = event.get("deal_id")
    if deal_id:
        deal = await redis_store.get_deal(deal_id)
        if deal:
            deal["updated_at"] = event["timestamp"]

            # Track agent runs (avoid duplicate entries)
            agent_type = event.get("agent_type", "unknown")
            if agent_type not in deal.get("agents_run", []):
                deal["agents_run"] = deal.get("agents_run", []) + [agent_type]

            # Track per-agent confidence for final score calculation
            if "confidence" in event:
                if "_confidence_scores" not in deal:
                    deal["_confidence_scores"] = {}
                deal["_confidence_scores"][agent_type] = float(event["confidence"])

            # Use explicit final_score if provided
            if event.get("final_score") is not None:
                deal["final_score"] = float(event["final_score"])
                deal["status"] = "completed"
                deal["current_stage"] = "completed"

            # Auto-complete fallback: mark done when at least 4 agents have run
            agents_done = set(deal.get("agents_run", []))
            if len(agents_done) >= 4 and deal["status"] != "completed":
                # Compute score from collected confidences
                scores = list(deal.get("_confidence_scores", {}).values())
                if scores:
                    deal["final_score"] = round(sum(scores) / len(scores), 4)
                else:
                    deal["final_score"] = 0.75  # reasonable default
                deal["status"] = "completed"
                deal["current_stage"] = "completed"

            await redis_store.save_deal(deal_id, deal)

    return {"status": "logged"}


@app.get("/api/v1/deals/{deal_id}/report")
async def generate_deal_report(deal_id: str, format: str = "pdf"):
    """
    Generate a McKinsey-style report for a deal.
    Supported formats: pptx, xlsx, pdf
    """
    from fastapi.responses import Response
    from app.core.reports.report_generator import (
        generate_pptx,
        generate_excel,
        generate_pdf,
    )

    redis_store = RedisStore.get_instance()
    deal = await redis_store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    import re

    # Collect agent results from activity log
    activities = await redis_store.get_deal_activity(deal_id)
    agent_results = []
    seen = set()
    for evt in activities:
        if evt.get("agent_type") not in seen:
            seen.add(evt["agent_type"])
            agent_results.append(evt)

    # Sanitize company name for Safe HTTP Headers
    raw_name = deal.get("target_company", "report")
    safe_name = re.sub(r"[^A-Za-z0-9]", "_", raw_name)
    # Collapse multiple underscores
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")
    if not safe_name:
        safe_name = "report"

    # Run Business Analyst here to format the final delivery payload dynamically
    from app.agents.base import get_agent_registry

    registry = get_agent_registry()
    ba_agent = registry.get("business_analyst")
    analyst_data = {}

    if ba_agent:
        logger.info("Executing Business Analyst formatting layer before download...")
        try:
            ba_result = await ba_agent.run(
                "Format report payload",
                context={"deal_id": deal_id, "deal_data": agent_results},
            )
            if ba_result.success:
                analyst_data = ba_result.data
        except Exception as e:
            logger.error("Business Analyst failed during download", error=str(e))

    fmt = format.lower()

    # Query Knowledge Base for context
    try:
        from app.core.memory.pageindex_client import get_pageindex_client
        from app.core.reports.report_generator import KBReportEnricher
        kb = get_pageindex_client()
        enricher = KBReportEnricher(kb)
        kb_context = await enricher.get_company_context(
            deal.get("target_company", ""),
            deal.get("industry", "")
        )
        format_context = await enricher.get_formatting_context(deal.get("name", ""))
        kb_references = enricher.get_references()
        
        analyst_data["_rag_context"] = {
            "kb_context": kb_context,
            "format_context": format_context,
            "references": kb_references,
            "chunks_used": len(kb_references)
        }
    except Exception as e:
        logger.warning(f"Failed to enrich report with KB data: {e}")

    # Fetch provenance records to embed in the report for auditing/footnotes
    from app.core.provenance import get_provenance_collector

    provenance_records = await get_provenance_collector().get_records(deal_id)
    deal_stage = deal.get("current_stage", "deep_dive")

    if fmt == "pptx":
        content = generate_pptx(
            deal, analyst_data, agent_results, provenance_records, deal_stage
        )
        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        filename = f"DealForge_{safe_name}.pptx"
    elif fmt in ("xlsx", "excel"):
        content = generate_excel(
            deal, analyst_data, agent_results, provenance_records, deal_stage
        )
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"DealForge_{safe_name}.xlsx"
    elif fmt == "pdf":
        content = generate_pdf(
            deal, analyst_data, agent_results, provenance_records, deal_stage
        )
        media_type = "application/pdf"
        filename = f"DealForge_{safe_name}.pdf"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use pptx, xlsx, or pdf.",
        )

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════
#  Document Hub — Generate Once, Download Instantly
# ══════════════════════════════════════════════════════════════════


@app.post("/api/v1/deals/{deal_id}/documents/generate")
async def generate_deal_documents(deal_id: str):
    """
    Generate & cache all report formats (PPTX, Excel, PDF) for a deal.
    
    This runs the BusinessAnalyst formatting layer and KB enrichment ONCE,
    then generates all 3 formats and caches them in Redis for instant downloads.
    """
    from fastapi.responses import JSONResponse
    from app.core.document_store import DocumentStore
    from app.core.reports.report_generator import (
        generate_pptx,
        generate_excel,
        generate_pdf,
    )

    redis_store = RedisStore.get_instance()
    doc_store = DocumentStore.get_instance()
    deal = await redis_store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    import re

    # ── Step 1: Collect agent results (ONCE) ──
    activities = await redis_store.get_deal_activity(deal_id)
    agent_results = []
    seen = set()
    for evt in activities:
        if evt.get("agent_type") not in seen:
            seen.add(evt["agent_type"])
            agent_results.append(evt)

    # ── Step 2: Run BusinessAnalyst formatting layer (ONCE) ──
    from app.agents.base import get_agent_registry as _get_registry

    registry = _get_registry()
    ba_agent = registry.get("business_analyst")
    analyst_data = {}

    if ba_agent:
        logger.info("Document Hub: Running Business Analyst formatting layer...")
        try:
            ba_result = await ba_agent.run(
                "Format report payload",
                context={"deal_id": deal_id, "deal_data": agent_results},
            )
            if ba_result.success:
                analyst_data = ba_result.data
        except Exception as e:
            logger.error("Business Analyst failed during doc generation", error=str(e))

    # ── Step 3: Enrich with Knowledge Base (ONCE) ──
    try:
        from app.core.memory.pageindex_client import get_pageindex_client
        from app.core.reports.report_generator import KBReportEnricher

        kb = get_pageindex_client()
        enricher = KBReportEnricher(kb)
        kb_context = await enricher.get_company_context(
            deal.get("target_company", ""), deal.get("industry", "")
        )
        format_context = await enricher.get_formatting_context(deal.get("name", ""))
        kb_references = enricher.get_references()

        analyst_data["_rag_context"] = {
            "kb_context": kb_context,
            "format_context": format_context,
            "references": kb_references,
            "chunks_used": len(kb_references),
        }
    except Exception as e:
        logger.warning(f"Failed to enrich with KB data: {e}")

    # ── Step 4: Fetch provenance (ONCE) ──
    from app.core.provenance import get_provenance_collector

    provenance_records = await get_provenance_collector().get_records(deal_id)
    deal_stage = deal.get("current_stage", "deep_dive")

    # ── Step 5: Sanitize filename ──
    raw_name = deal.get("target_company", "report")
    safe_name = re.sub(r"[^A-Za-z0-9]", "_", raw_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("_") or "report"

    # ── Step 6: Generate all 3 formats & cache ──
    formats_generated = []
    errors = []
    metadata = {
        "target_company": deal.get("target_company", "Unknown"),
        "deal_name": deal.get("name", "Unknown"),
        "agents_count": len(agent_results),
        "safe_filename": safe_name,
    }

    format_generators = {
        "pptx": generate_pptx,
        "xlsx": generate_excel,
        "pdf": generate_pdf,
    }

    for fmt, generator in format_generators.items():
        try:
            content = generator(
                deal, analyst_data, agent_results, provenance_records, deal_stage
            )
            await doc_store.save_document(deal_id, fmt, content, metadata)
            formats_generated.append(fmt)
            logger.info(f"Document Hub: Generated {fmt.upper()}", deal_id=deal_id)
        except Exception as e:
            errors.append({"format": fmt, "error": str(e)})
            logger.error(f"Document Hub: Failed to generate {fmt}", error=str(e))

    # Return the manifest
    manifest = await doc_store.list_documents(deal_id)

    return {
        "deal_id": deal_id,
        "status": "complete" if not errors else "partial",
        "formats_generated": formats_generated,
        "errors": errors,
        "documents": manifest,
    }


@app.get("/api/v1/deals/{deal_id}/documents")
async def list_deal_documents(deal_id: str):
    """
    Return a manifest of all available cached documents for a deal.
    Each entry includes format, size, generated timestamp, and status.
    """
    from app.core.document_store import DocumentStore

    redis_store = RedisStore.get_instance()
    deal = await redis_store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    doc_store = DocumentStore.get_instance()
    documents = await doc_store.list_documents(deal_id)

    return {
        "deal_id": deal_id,
        "deal_name": deal.get("name", "Unknown"),
        "target_company": deal.get("target_company", "Unknown"),
        "has_documents": len(documents) > 0,
        "documents": documents,
    }


@app.get("/api/v1/deals/{deal_id}/documents/bundle")
async def download_deal_bundle(deal_id: str):
    """
    Download a ZIP bundle containing all cached documents for a deal.
    """
    import zipfile
    import io
    from fastapi.responses import Response
    from app.core.document_store import DocumentStore

    doc_store = DocumentStore.get_instance()
    documents = await doc_store.list_documents(deal_id)

    if not documents:
        raise HTTPException(
            status_code=404,
            detail="No cached documents found. Call POST /documents/generate first.",
        )

    # Build ZIP in memory
    zip_buffer = io.BytesIO()
    safe_name = documents[0].get("safe_filename", "report")

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_meta in documents:
            fmt = doc_meta["format"]
            content = await doc_store.get_document(deal_id, fmt)
            if content:
                filename = f"DealForge_{safe_name}.{fmt}"
                zf.writestr(filename, content)

    zip_buffer.seek(0)
    zip_filename = f"DealForge_{safe_name}_Reports.zip"

    return Response(
        content=zip_buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@app.get("/api/v1/deals/{deal_id}/documents/{fmt}")
async def download_deal_document(deal_id: str, fmt: str):
    """
    Download a single cached document by format (pdf, pptx, xlsx).
    Returns cached bytes instantly — no regeneration.
    """
    from fastapi.responses import Response
    from app.core.document_store import DocumentStore

    doc_store = DocumentStore.get_instance()
    fmt = DocumentStore.get_extension(fmt.lower())

    if fmt not in ("pptx", "xlsx", "pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {fmt}. Use pptx, xlsx, or pdf.",
        )

    # Try cache first
    content = await doc_store.get_document(deal_id, fmt)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached {fmt.upper()} document found. Call POST /documents/generate first.",
        )

    meta = await doc_store.get_document_meta(deal_id, fmt)
    safe_name = (meta or {}).get("safe_filename", "report")
    filename = f"DealForge_{safe_name}.{fmt}"

    return Response(
        content=content,
        media_type=DocumentStore.get_content_type(fmt),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════
#  Conversation Persistence Endpoints (Redis-backed)
# ══════════════════════════════════════════════════════════════════


@app.get("/api/v1/conversations")
async def list_conversations():
    """List all chat conversations from Redis."""
    redis_store = RedisStore.get_instance()
    conversations = await redis_store.list_conversations()
    return {"conversations": conversations}


@app.get("/api/v1/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get a single conversation by ID."""
    redis_store = RedisStore.get_instance()
    conv = await redis_store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.post("/api/v1/conversations")
async def create_conversation(request: Request):
    """Create or save a full conversation."""
    body = await request.json()
    conv_id = body.get("id")
    if not conv_id:
        raise HTTPException(status_code=400, detail="Conversation must have an 'id'")
    redis_store = RedisStore.get_instance()
    await redis_store.save_conversation(conv_id, body)
    return {"status": "saved", "id": conv_id}


@app.put("/api/v1/conversations/{conv_id}")
async def save_conversation(conv_id: str, request: Request):
    """Save/overwrite a full conversation (used by frontend sync)."""
    body = await request.json()
    body["id"] = conv_id  # Ensure ID consistency
    redis_store = RedisStore.get_instance()
    await redis_store.save_conversation(conv_id, body)
    return {"status": "saved", "id": conv_id}


@app.patch("/api/v1/conversations/{conv_id}")
async def update_conversation(conv_id: str, request: Request):
    """Partially update a conversation (title, add messages, etc.)."""
    redis_store = RedisStore.get_instance()
    conv = await redis_store.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    updates = await request.json()
    conv.update(updates)
    await redis_store.save_conversation(conv_id, conv)
    return {"status": "updated", "id": conv_id}


@app.delete("/api/v1/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation."""
    redis_store = RedisStore.get_instance()
    await redis_store.delete_conversation(conv_id)
    return {"status": "deleted", "id": conv_id}


@app.delete("/api/v1/conversations")
async def clear_all_conversations():
    """Delete all conversations."""
    redis_store = RedisStore.get_instance()
    await redis_store.clear_all_conversations()
    return {"status": "cleared"}


# ══════════════════════════════════════════════════════════════════
#  Knowledge Base / PageIndex Endpoints
# ══════════════════════════════════════════════════════════════════


@app.get("/api/v1/pageindex/stats")
async def pageindex_stats():
    """Return RAG index statistics for the Knowledge Base dashboard."""
    try:
        client = get_pageindex_client()
        raw = client.get_stats()
        return {
            "total_documents": raw.get("total_documents", 0),
            "total_nodes": raw.get("total_nodes", 0),
            "storage_dir": raw.get("storage_dir", "./storage"),
            "storage_size_mb": raw.get("storage_size_mb", 0),
        }
    except Exception as e:
        logger.error("pageindex_stats failed", error=str(e))
        return {
            "total_documents": 0,
            "total_nodes": 0,
            "storage_dir": "./storage",
            "storage_size_mb": 0,
        }


@app.get("/api/v1/pageindex/documents")
async def pageindex_documents():
    """List all indexed documents for the Knowledge Base dashboard."""
    try:
        client = get_pageindex_client()
        raw = client.get_stats()
        docs = raw.get("documents", [])
        return {
            "documents": docs,
            "mode": getattr(client, "mode", "local"),
        }
    except Exception as e:
        logger.error("pageindex_documents failed", error=str(e))
        return {"documents": [], "mode": "local"}


class _QueryBody(BaseModel):
    query: str
    top_k: int = 5
    deal_id: Optional[str] = None


@app.post("/api/v1/documents/query")
async def documents_query(body: _QueryBody):
    """Semantic search over the RAG Knowledge Base."""
    try:
        client = get_pageindex_client()
        filters = {"deal_id": body.deal_id} if body.deal_id else None
        chunks = await client.query(query=body.query, top_k=body.top_k, filters=filters)
        return {
            "query": body.query,
            "results": [
                {
                    "content": c.content,
                    "page": c.page_number,
                    "relevance": c.relevance_score,
                    "chunk_id": c.chunk_id,
                }
                for c in chunks
            ],
        }
    except Exception as e:
        logger.error("documents_query failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/documents/upload")
async def documents_upload(file: UploadFile = File(...), deal_id: Optional[str] = None):
    """Upload and index a document into the Knowledge Base."""
    import tempfile, os

    try:
        suffix = os.path.splitext(file.filename or ".txt")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        client = get_pageindex_client()
        metadata = {"original_filename": file.filename}
        if deal_id:
            metadata["deal_id"] = deal_id

        result = await client.ingest_document(tmp_path, metadata=metadata)

        os.unlink(tmp_path)

        return {
            "status": "indexed",
            "index_id": getattr(result, "index_id", ""),
            "document_id": getattr(result, "document_id", ""),
            "total_pages": getattr(result, "total_pages", 0),
            "total_chunks": getattr(result, "total_chunks", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/documents/upload/bulk")
async def documents_upload_bulk(
    files: List[UploadFile] = File(...), deal_id: Optional[str] = None
):
    """Bulk upload and index multiple documents into the Knowledge Base."""
    import tempfile, os

    client = get_pageindex_client()
    results = []

    for file in files:
        try:
            suffix = os.path.splitext(file.filename or ".txt")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            metadata = {"original_filename": file.filename}
            if deal_id:
                metadata["deal_id"] = deal_id

            res = await client.ingest_document(tmp_path, metadata=metadata)
            os.unlink(tmp_path)

            results.append(
                {
                    "filename": file.filename,
                    "status": "indexed",
                    "index_id": getattr(res, "index_id", ""),
                }
            )
        except Exception as e:
            logger.error(
                "bulk_upload_file_failed", filename=file.filename, error=str(e)
            )
            results.append(
                {"filename": file.filename, "status": "failed", "error": str(e)}
            )

    return {"results": results}


class URLIngestRequest(BaseModel):
    url: str
    deal_id: Optional[str] = None


class DirectoryIngestRequest(BaseModel):
    directory_path: str
    deal_id: Optional[str] = None


async def _index_directory_background(directory: str, deal_id: Optional[str]):
    try:
        from pathlib import Path
        import os

        client = get_pageindex_client()
        supported_extensions = {".pdf", ".docx", ".md", ".txt", ".markdown"}
        path = Path(directory)

        if not path.is_dir():
            logger.error("invalid_directory_path", path=directory)
            return

        files_to_index = []
        for root, _, files in os.walk(directory):
            for file in files:
                if Path(file).suffix.lower() in supported_extensions:
                    files_to_index.append(Path(root) / file)

        if not files_to_index:
            logger.warning("no_supported_files_found", directory=directory)
            return

        for file_path in files_to_index:
            try:
                metadata = {
                    "original_filename": file_path.name,
                    "source": "local_directory",
                    "directory_path": directory,
                }
                if deal_id:
                    metadata["deal_id"] = deal_id

                await client.ingest_document(str(file_path), metadata=metadata)
                logger.info("indexed_local_file", file=file_path.name)
            except Exception as e:
                logger.error(
                    "local_file_index_failed", file=file_path.name, error=str(e)
                )

        logger.info(
            "directory_indexing_complete",
            directory=directory,
            count=len(files_to_index),
        )
    except Exception as e:
        logger.error(
            "directory_indexing_fatal_error", directory=directory, error=str(e)
        )


@app.post("/api/v1/documents/directory")
async def documents_ingest_directory(
    request: DirectoryIngestRequest,
    background_tasks: __import__("fastapi").BackgroundTasks,
):
    """Ingest documents from a local directory in the background."""
    # We do NOT validate path.is_dir() here because the UI might send
    # a Windows path (e.g., C:\) while this backend runs in a Linux container.
    # The background task will attempt resolution and log any errors gracefully.

    background_tasks.add_task(
        _index_directory_background,
        request.directory_path,
        request.deal_id,
    )

    return {
        "status": "indexing_started",
        "message": f"Background indexing started for directory: {request.directory_path}",
    }


@app.post("/api/v1/documents/url")
async def documents_ingest_url(request: URLIngestRequest):
    """Ingest content from a URL directly into the Knowledge Base."""
    try:
        from app.core.tools.scraper_tool import WebScraperTool

        scraper = WebScraperTool()
        result = await scraper.execute(request.url)
        if not result.success:
            raise HTTPException(
                status_code=400, detail=f"Scraper failed: {result.error}"
            )

        client = get_pageindex_client()
        metadata = {"original_filename": request.url, "source": "url"}
        if request.deal_id:
            metadata["deal_id"] = request.deal_id

        res = await client.ingest_text(result.data, metadata=metadata)

        return {
            "status": "indexed",
            "url": request.url,
            "index_id": getattr(res, "index_id", ""),
        }
    except Exception as e:
        logger.error("url_ingest_failed", url=request.url, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/documents/{index_id}")
async def documents_delete(index_id: str):
    """Delete an indexed document from the Knowledge Base."""
    try:
        client = get_pageindex_client()
        result = await client.delete_index(index_id)
        if result:
            return {"status": "deleted", "index_id": index_id}
        else:
            raise HTTPException(
                status_code=404, detail="Index not found or could not be deleted"
            )
    except Exception as e:
        logger.error("documents_delete_failed", index_id=index_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/deals/{deal_id}/run")
async def run_deal_workflow(deal_id: str):
    """Run complete deal workflow"""
    logger.info("Running deal workflow", deal_id=deal_id)

    orchestrator = get_orchestrator_instance()

    # Run the workflow
    final_state = await orchestrator.run_deal(
        deal_id=deal_id, deal_name=f"Deal-{deal_id[:8]}", context={"deal_id": deal_id}
    )

    return {
        "deal_id": deal_id,
        "status": final_state.get("current_stage"),
        "final_score": final_state.get("final_score"),
        "final_recommendation": final_state.get("final_recommendation"),
        "stage_history": final_state.get("stage_history", []),
        "completed_at": final_state.get("completed_at"),
    }


@app.get("/api/v1/deals/{deal_id}/status")
async def get_deal_status(deal_id: str):
    """Get current deal workflow status"""
    return {
        "deal_id": deal_id,
        "status": "in_progress",  # Would fetch from DB
        "current_stage": "analysis",
    }


@app.get("/api/v1/deals/{deal_id}/results")
async def get_deal_results(deal_id: str):
    """Get complete deal analysis results"""
    # This would fetch from database in production
    return {
        "deal_id": deal_id,
        "financial_analysis": {},
        "legal_analysis": {},
        "risk_assessment": {},
        "market_research": {},
        "final_score": None,
        "recommendation": None,
    }


# ===== Agent Routes =====


@app.get("/api/v1/agents")
async def list_agents():
    """List all available agents"""
    registry = get_agent_registry()
    return {"agents": registry.list_agents()}


@app.post("/api/v1/agents/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest):
    """Run a specific agent"""
    registry = get_agent_registry()
    agent = registry.get(request.agent_type)

    if not agent:
        raise HTTPException(
            status_code=404, detail=f"Agent '{request.agent_type}' not found"
        )

    logger.info("Running agent", agent_type=request.agent_type, task=request.task)

    result = await agent.run(request.task, context=request.context)

    return AgentRunResponse(
        agent_type=request.agent_type,
        success=result.success,
        data=result.data,
        reasoning=result.reasoning,
        confidence=result.confidence,
        provider=agent.llm.__class__.__name__.lower().replace("client", ""),
        execution_time_ms=result.execution_time_ms,
    )


# ===== Document & PageIndex Routes =====


@app.post("/api/v1/documents/upload")
async def upload_document(deal_id: str, file: UploadFile = File(...)):
    """Upload and index a document"""
    logger.info("Uploading document", deal_id=deal_id, filename=file.filename)

    # Save file temporarily
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Index with PageIndex
    pageindex = get_pageindex_client()

    try:
        index_result = await pageindex.ingest_document(
            temp_path, metadata={"deal_id": deal_id, "filename": file.filename}
        )

        return DocumentUploadResponse(
            document_id=str(uuid.uuid4()),
            filename=file.filename,
            pageindex_id=index_result.index_id,
            status="indexed",
        )

    except Exception as e:
        logger.error("Document indexing failed", error=str(e))
        return DocumentUploadResponse(
            document_id=str(uuid.uuid4()), filename=file.filename, status="failed"
        )


@app.post("/api/v1/documents/query")
async def query_documents(request: DocumentQueryRequest):
    """Query indexed documents"""
    pageindex = get_pageindex_client()
    query = request.query

    try:
        chunks = await pageindex.query(query, top_k=5)

        return {
            "query": query,
            "results": [
                {
                    "content": chunk.content,
                    "page": chunk.page_number,
                    "relevance": chunk.relevance_score,
                }
                for chunk in chunks
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/pageindex/stats")
async def pageindex_stats():
    """Get self-hosted PageIndex storage stats"""
    pageindex = get_pageindex_client()
    return pageindex.get_stats()


@app.get("/api/v1/pageindex/documents")
async def pageindex_documents(deal_id: Optional[str] = None):
    """List all indexed documents"""
    pageindex = get_pageindex_client()
    if pageindex._local_service:
        docs = pageindex._local_service.list_documents(deal_id)
        return {
            "mode": "local",
            "documents": [
                {
                    "doc_id": d.doc_id,
                    "filename": d.filename,
                    "file_type": d.file_type,
                    "total_pages": d.total_pages,
                    "total_nodes": d.total_nodes,
                    "created_at": d.created_at,
                    "metadata": d.metadata,
                }
                for d in docs
            ],
        }
    return {"mode": "cloud", "documents": []}


@app.get("/api/v1/models/routing")
async def model_routing():
    """Show which LLM provider each agent uses with health status"""
    from app.core.llm.model_router import get_model_router

    router = get_model_router()
    table = router.get_routing_table()
    health_table = router.get_routing_table_with_health()
    return {
        "strategy": "local-first with cloud fallback",
        "routing_table": table,
        "health": health_table,
        "agents": list(table.keys()),
        "cloud_agents": [
            k for k, v in table.items() if v in ("gemini", "openai", "mistral")
        ],
        "local_agents": [k for k, v in table.items() if v in ("ollama", "lmstudio")],
        "note": "Agents assigned to local LLMs will auto-fallback to cloud if the local provider is offline.",
    }


# ===== Dynamic Model Discovery =====


@app.get("/api/v1/models/available")
async def list_available_models():
    """
    Query all configured LLM providers for their available models IN PARALLEL.
    Each provider has its own timeout so one stall won't block the others.
    Returns a dict keyed by provider with lists of model info.
    """
    import asyncio
    import httpx as _httpx

    settings = get_settings()

    async def _get_ollama(base_url: str):
        import os

        if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
            base_url = base_url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )
        try:
            async with _httpx.AsyncClient(timeout=4.0) as c:
                r = await c.get(f"{base_url}/api/tags")
                if r.status_code == 200:
                    models = r.json().get("models", [])
                    return (
                        "ollama",
                        {
                            "status": "online",
                            "models": [
                                {
                                    "id": m.get("name", ""),
                                    "name": m.get("name", "").split(":")[0],
                                    "parameter_size": m.get("details", {}).get(
                                        "parameter_size", ""
                                    ),
                                    "quantization": m.get("details", {}).get(
                                        "quantization_level", ""
                                    ),
                                    "family": m.get("details", {}).get("family", ""),
                                }
                                for m in models
                            ],
                        },
                    )
                return (
                    "ollama",
                    {"status": "error", "models": [], "error": f"HTTP {r.status_code}"},
                )
        except Exception as e:
            return ("ollama", {"status": "offline", "models": [], "error": str(e)})

    async def _get_lmstudio(base_url: str):
        import os

        if os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"):
            base_url = base_url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )
        try:
            async with _httpx.AsyncClient(timeout=4.0) as c:
                r = await c.get(f"{base_url}/models")
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    return (
                        "lmstudio",
                        {
                            "status": "online",
                            "models": [
                                {
                                    "id": m.get("id", ""),
                                    "name": (
                                        m.get("id", "").split("/")[-1]
                                        if "/" in m.get("id", "")
                                        else m.get("id", "")
                                    ),
                                    "owned_by": m.get("owned_by", ""),
                                }
                                for m in models
                            ],
                        },
                    )
                return (
                    "lmstudio",
                    {"status": "error", "models": [], "error": f"HTTP {r.status_code}"},
                )
        except Exception as e:
            return ("lmstudio", {"status": "offline", "models": [], "error": str(e)})

    async def _get_gemini(api_key: str):
        if not api_key:
            return (
                "gemini",
                {"status": "no_key", "models": [], "error": "GEMINI_API_KEY not set"},
            )
        try:
            async with _httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(
                    "https://generativelanguage.googleapis.com/v1/models",
                    params={"key": api_key, "pageSize": 100},
                )
                if r.status_code == 200:
                    all_models = r.json().get("models", [])
                    models = [
                        {
                            "id": m.get("name", "").replace("models/", ""),
                            "name": m.get("displayName", ""),
                            "input_token_limit": m.get("inputTokenLimit", 0),
                            "output_token_limit": m.get("outputTokenLimit", 0),
                        }
                        for m in all_models
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                    return ("gemini", {"status": "online", "models": models})
                return (
                    "gemini",
                    {"status": "error", "models": [], "error": f"HTTP {r.status_code}"},
                )
        except Exception as e:
            return ("gemini", {"status": "error", "models": [], "error": str(e)})

    async def _get_mistral(api_key: str):
        if not api_key:
            return (
                "mistral",
                {"status": "no_key", "models": [], "error": "MISTRAL_API_KEY not set"},
            )
        try:
            async with _httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    return (
                        "mistral",
                        {
                            "status": "online",
                            "models": [
                                {
                                    "id": m.get("id", ""),
                                    "name": m.get("id", "").replace("-", " ").title(),
                                    "owned_by": m.get("owned_by", "mistralai"),
                                }
                                for m in models
                            ],
                        },
                    )
                return (
                    "mistral",
                    {"status": "error", "models": [], "error": f"HTTP {r.status_code}"},
                )
        except Exception as e:
            return ("mistral", {"status": "error", "models": [], "error": str(e)})

    async def _get_openai(api_key: str):
        if not api_key:
            return (
                "openai",
                {"status": "no_key", "models": [], "error": "OPENAI_API_KEY not set"},
            )
        try:
            async with _httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if r.status_code == 200:
                    models = r.json().get("data", [])
                    chat_models = [
                        {
                            "id": m.get("id", ""),
                            "name": m.get("id", ""),
                            "owned_by": m.get("owned_by", ""),
                        }
                        for m in models
                        if any(
                            k in m.get("id", "").lower() for k in ("gpt", "o3", "o1")
                        )
                    ]
                    return ("openai", {"status": "online", "models": chat_models})
                return (
                    "openai",
                    {"status": "error", "models": [], "error": f"HTTP {r.status_code}"},
                )
        except Exception as e:
            return ("openai", {"status": "error", "models": [], "error": str(e)})

    # Query all providers IN PARALLEL â€” each with its own individual timeout
    results = await asyncio.gather(
        asyncio.wait_for(
            _get_ollama(getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")),
            timeout=5,
        ),
        asyncio.wait_for(
            _get_lmstudio(
                getattr(settings, "LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
            ),
            timeout=5,
        ),
        asyncio.wait_for(_get_gemini(settings.GEMINI_API_KEY or ""), timeout=10),
        asyncio.wait_for(_get_mistral(settings.MISTRAL_API_KEY or ""), timeout=10),
        asyncio.wait_for(_get_openai(settings.OPENAI_API_KEY or ""), timeout=10),
        return_exceptions=True,
    )

    output = {}
    for item in results:
        if isinstance(item, Exception):
            # Timeout or unexpected error â€” pick a name from exception context
            continue
        key, data = item
        output[key] = data

    return output


# ===== CV and LMT Workflow Endpoints =====


class CVSimulationRequest(BaseModel):
    """Request for GP-Led CV simulation"""

    total_nav: float
    existing_debt: float
    projected_cash_flows: List[float]
    gp_carried_interest: float = 0.20
    preferred_return: float = 0.08


@app.post("/api/v1/workflows/cv-simulation")
async def run_cv_simulation(request: CVSimulationRequest):
    """Run GP-Led Continuation Vehicle waterfall simulation"""
    from app.workflows.gp_led_cv import CVWaterfallSolver, CVSimulationConfig

    config = CVSimulationConfig(
        lpa_document_id="",
        bid_spread_data={},
        gp_carried_interest=request.gp_carried_interest,
        preferred_return=request.preferred_return,
    )
    solver = CVWaterfallSolver(config)

    result = solver.solve(
        total_nav=request.total_nav,
        existing_debt=request.existing_debt,
        projected_cash_flows=request.projected_cash_flows,
    )

    return result


class LMTScanRequest(BaseModel):
    """Request for LMT loophole scan"""

    agreement_text: str


@app.post("/api/v1/workflows/lmt-scan")
async def run_lmt_scan(request: LMTScanRequest):
    """Scan credit agreement for liability management loopholes"""
    from app.workflows.lmt_simulation import LoopholeDetector

    detector = LoopholeDetector()
    findings = detector.scan(request.agreement_text)

    return {
        "total_findings": len(findings),
        "findings": findings,
        "loophole_types": list(set(f["loophole_type"] for f in findings)),
    }


class MonteCarloRequest(BaseModel):
    """Request for Monte Carlo recovery simulation"""

    tranches: List[dict]
    total_collateral: float
    num_simulations: int = 10_000


@app.post("/api/v1/workflows/monte-carlo")
async def run_monte_carlo(request: MonteCarloRequest):
    """Run Monte Carlo recovery simulation across capital structure"""
    from app.workflows.lmt_simulation import MonteCarloRecoveryModel, LMTConfig

    config = LMTConfig(num_simulations=request.num_simulations)
    model = MonteCarloRecoveryModel(config)

    result = model.run_full_capital_structure(
        tranches=request.tranches,
        total_collateral=request.total_collateral,
    )

    return result


# ===== WebSocket for Real-time Updates =====


class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "subscribe_deal":
                deal_id = message.get("deal_id")
                await websocket.send_json({"type": "subscribed", "deal_id": deal_id})

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif message.get("type") == "heartbeat":
                # Tax Agent heartbeat: force immediate IRR re-computation
                deal_id = message.get("deal_id")
                logger.info(
                    "Heartbeat received â€” triggering IRR re-computation",
                    deal_id=deal_id,
                )
                await manager.broadcast(
                    {
                        "type": "heartbeat_ack",
                        "deal_id": deal_id,
                        "action": "irr_recompute_triggered",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            elif message.get("type") == "escalation_query":
                deal_id = message.get("deal_id")
                await websocket.send_json(
                    {
                        "type": "escalation_status",
                        "deal_id": deal_id,
                        "status": "active",
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ===== Codex Integration Routes =====


@app.post("/api/v1/codex/generate")
async def generate_code(request: dict):
    """Generate code using OpenAI Codex"""
    from app.core.llm.gemini_client import OpenAIClient

    client = OpenAIClient(model=settings.CODEX_MODEL)

    try:
        result = await client.generate_code(
            prompt=request.get("prompt", ""), language=request.get("language", "python")
        )

        return {"generated_code": result, "language": request.get("language", "python")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
#  Task Management API (Project Manager / Todo Lists)
# ═══════════════════════════════════════════════════════════

from app.core.tasks.task_manager import get_task_manager


@app.post("/api/v1/deals/{deal_id}/tasks")
async def create_todo_list(deal_id: str, body: Dict[str, Any]):
    """Create a structured todo list for a deal analysis."""
    tm = get_task_manager()
    try:
        # Use ProjectManagerAgent if available, else create from body
        items = body.get("items", [])
        title = body.get("title", f"Deal Analysis: {deal_id}")
        description = body.get("description", "")

        if not items:
            # Auto-generate using ProjectManagerAgent template
            from app.agents.project_manager import ProjectManagerAgent

            pm = ProjectManagerAgent()
            result = await pm.run(
                task=body.get("task", f"Analyze deal {deal_id}"),
                context={
                    "deal_id": deal_id,
                    "company_name": body.get("company_name", deal_id),
                },
            )
            if result.success:
                return result.data
            raise HTTPException(status_code=500, detail=result.reasoning)

        todo = await tm.create_todo_list(
            deal_id=deal_id, title=title, items=items, description=description
        )
        return todo.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/deals/{deal_id}/tasks")
async def get_deal_tasks(deal_id: str):
    """Get all todo lists for a deal."""
    tm = get_task_manager()
    lists = await tm.get_lists_for_deal(deal_id)
    return {"deal_id": deal_id, "todo_lists": [tl.to_dict() for tl in lists]}


@app.get("/api/v1/tasks/{list_id}")
async def get_todo_list(list_id: str):
    """Get a specific todo list."""
    tm = get_task_manager()
    todo = await tm.get_todo_list(list_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo list not found")
    return todo.to_dict()


@app.put("/api/v1/tasks/{list_id}/items/{task_id}")
async def update_task(list_id: str, task_id: str, body: Dict[str, Any]):
    """Update a specific task (edit title, description, reassign agent, change priority)."""
    tm = get_task_manager()
    item = await tm.update_task(list_id, task_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="Task not found")
    return item.to_dict()


@app.delete("/api/v1/tasks/{list_id}/items/{task_id}")
async def delete_task(list_id: str, task_id: str):
    """Remove a task from a list."""
    tm = get_task_manager()
    if not await tm.delete_task(list_id, task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


@app.post("/api/v1/tasks/{list_id}/items")
async def add_task(list_id: str, body: Dict[str, Any]):
    """Add a new task to an existing list."""
    tm = get_task_manager()
    item = await tm.add_task(list_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="Todo list not found")
    return item.to_dict()


@app.post("/api/v1/tasks/{list_id}/approve")
async def approve_todo_list(list_id: str):
    """Approve a todo list for execution."""
    tm = get_task_manager()
    todo = await tm.approve_list(list_id)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo list not found")
    return {"success": True, "status": todo.status}


@app.post("/api/v1/tasks/{list_id}/execute")
async def execute_todo_list(list_id: str):
    """Execute all pending tasks in the approved todo list."""
    from app.agents.project_manager import ProjectManagerAgent

    pm = ProjectManagerAgent()
    result = await pm.execute_all(list_id, agent_registry=get_agent_registry())
    return result


@app.post("/api/v1/tasks/{list_id}/reorder")
async def reorder_tasks(list_id: str, body: Dict[str, Any]):
    """Reorder tasks in a list."""
    tm = get_task_manager()
    task_ids = body.get("task_ids", [])
    if not await tm.reorder_tasks(list_id, task_ids):
        raise HTTPException(status_code=404, detail="Todo list not found")
    return {"success": True}


# ═══════════════════════════════════════════════════════════
#  Knowledge Base Ingestion API
# ═══════════════════════════════════════════════════════════


@app.post("/api/v1/knowledge/ingest")
async def ingest_knowledge_base(body: Optional[Dict[str, Any]] = None):
    """Batch-ingest knowledge base documents into RAG."""
    from app.core.tasks.knowledge_ingestion import KnowledgeIngestionService

    body = body or {}

    pageindex = get_pageindex_client()
    service = KnowledgeIngestionService(pageindex)

    directory = body.get("directory")
    if directory:
        result = await service.ingest_directory(directory)
    else:
        result = await service.ingest_all_knowledge_bases()

    return {"status": "completed", "results": result}


@app.get("/api/v1/knowledge/status")
async def knowledge_status():
    """Get knowledge base ingestion status."""
    pageindex = get_pageindex_client()
    try:
        stats = pageindex.get_stats()
        return {"status": "available", "stats": stats}
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


@app.get("/api/v1/knowledge/search")
async def knowledge_search(q: str, top_k: int = 5):
    """Search the knowledge base."""
    pageindex = get_pageindex_client()
    try:
        results = await pageindex.query(query=q, top_k=top_k)
        return {
            "query": q,
            "results": (
                [
                    {
                        "content": r.content[:500],
                        "metadata": r.metadata,
                        "score": r.relevance_score,
                    }
                    for r in results
                ]
                if results
                else []
            ),
        }
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  Infographic / Chart Generation API
# ═══════════════════════════════════════════════════════════


@app.post("/api/v1/charts/preview")
async def generate_chart_preview(body: Dict[str, Any]):
    """Generate a chart preview from data."""
    from app.core.reports.infographic_engine import InfographicEngine
    import base64

    chart_type = body.get("type", "football_field")
    data = body.get("data", {})

    try:
        engine = InfographicEngine()
        if chart_type == "football_field":
            png = engine.football_field_chart(data.get("valuations", []))
        elif chart_type == "waterfall":
            png = engine.revenue_waterfall(
                data.get("labels", []), data.get("values", [])
            )
        elif chart_type == "risk_heatmap":
            png = engine.risk_heatmap(data.get("risk_data", {}))
        elif chart_type == "radar":
            png = engine.deal_score_radar(data.get("scores", {}))
        elif chart_type == "sensitivity":
            png = engine.sensitivity_table(
                data.get("row_label", ""),
                data.get("col_label", ""),
                data.get("row_values", []),
                data.get("col_values", []),
                data.get("matrix", []),
            )
        elif chart_type == "bubble":
            png = engine.market_position_bubble(data.get("companies", []))
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown chart type: {chart_type}"
            )

        return {
            "chart_type": chart_type,
            "image_base64": base64.b64encode(png).decode("utf-8"),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
#  Startup Intelligence API (Crunchbase / BrightData scraping)
# ═══════════════════════════════════════════════════════════


@app.get("/api/v1/startups/search")
async def search_startup(company: str, depth: str = "standard"):
    """Research a startup using public data scraping (no API key needed)."""
    from app.core.tools.startup_intelligence_tool import StartupIntelligenceTool

    tool = StartupIntelligenceTool()
    result = await tool.execute_async(company=company, depth=depth)
    if result.success:
        return result.data
    raise HTTPException(status_code=500, detail=result.error or "Search failed")


# ═══════════════════════════════════════════════════════════
#  Scrum Master Chat API — Plan + Execute via ProjectManager
# ═══════════════════════════════════════════════════════════


@app.post("/api/v1/chat/clarify")
async def chat_clarify(request: Request):
    """
    Scrum Master Phase 1+2: Look at user prompt and determine data needs + clarifying questions.
    Limited to MAX_CLARIFICATION_ROUNDS (default 1) to prevent infinite loops.
    """
    from app.core.validation.chat_guard import check_prompt

    MAX_CLARIFICATION_ROUNDS = 1

    body = await request.json()
    prompt = body.get("prompt", "")

    # ---- guardrail: validate prompt early ----
    guard = check_prompt(prompt)
    if not guard["valid"]:
        # FastAPI will automatically serialize this dict to JSON
        return {"error": "invalid_prompt", "details": guard}

    deal_id = body.get("deal_id", "unknown")
    company_name = body.get("company_name", "Target Company")
    clarification_round = body.get("clarification_round", 0)

    # ── Guard: skip clarification after max rounds ──
    if clarification_round >= MAX_CLARIFICATION_ROUNDS:
        logger.info(
            "clarification_skipped",
            reason="max_rounds_reached",
            round=clarification_round,
            deal_id=deal_id,
        )
        return {
            "phase": "clarification",
            "clarifying_questions": [],
            "skip_reason": "Maximum clarification rounds reached. Proceeding to planning.",
        }

    from app.agents.project_manager import ProjectManagerAgent
    from app.core.llm.model_router import get_model_router
    from app.core.llm import get_llm_client
    from app.config import get_settings

    settings = get_settings()
    llms_configured = any(
        [
            settings.GEMINI_API_KEY,
            settings.OPENAI_API_KEY,
            settings.MISTRAL_API_KEY,
        ]
    )

    # If no local mode is explicitly chosen and no API keys exist, warn the user
    # (Ollama is usually active by default, but we should make sure they have a real model)
    if (
        not llms_configured
        and not settings.OLLAMA_BASE_URL
        and not settings.LMSTUDIO_BASE_URL
    ):
        return {
            "phase": "clarification",
            "clarifying_questions": [
                {
                    "question": "No AI Models are configured. Please go to Settings and add an API key (Gemini, OpenAI, Mistral) or a Local LLM URL.",
                    "reasoning": "The application requires an active LLM connection to function.",
                }
            ],
        }

    from app.core.mcp import get_provider_status

    mcp_status = get_provider_status()
    configured_mcps = [p for p in mcp_status if p.get("configured")]

    router = get_model_router()
    provider, _ = await router.get_provider_with_fallback("project_manager")
    llm_client = get_llm_client(provider)

    pm = ProjectManagerAgent(llm_client=llm_client)
    result = await pm.generate_clarifying_questions(
        prompt,
        context={
            "deal_id": deal_id,
            "company_name": company_name,
            "user_prompt": prompt,
            "available_mcp_providers": configured_mcps,
        },
    )
    return result


@app.post("/api/v1/chat/clarify/feedback")
async def chat_clarify_feedback(request: Request):
    """
    Store clarification Q&A pairs and deal outcome scores into memory.
    Powers Tier 2 (self-learning memory) and Tier 3 (RL quality signal).

    Body:
        deal_type: str
        questions: list of question dicts that were asked
        user_answer: str — the user's combined reply
        task_score: float (0.0–1.0) — optional agent confidence score
        user_rating: "positive" | "negative" | null — optional user rating
    """
    from app.core.memory.clarification_memory import ClarificationMemory
    from app.core.memory.question_quality_store import QuestionQualityStore

    body = await request.json()
    deal_type = body.get("deal_type", "general")
    questions = body.get("questions", [])
    user_answer = body.get("user_answer", "")
    task_score = float(body.get("task_score", 0.75))
    user_rating = body.get("user_rating", None)

    # Tier 2: store Q&A pair for future memory recall
    memory = ClarificationMemory()
    if questions and user_answer:
        memory.store(deal_type, questions, user_answer)

    # Tier 3: record outcome into quality store
    quality = QuestionQualityStore()
    qt_asked = [q.get("type", "unknown") for q in questions]
    if qt_asked:
        quality.record_outcome(deal_type, qt_asked, task_score, user_rating)

    logger.info(
        "clarify_feedback_stored",
        deal_type=deal_type,
        n_questions=len(questions),
        task_score=task_score,
        user_rating=user_rating,
    )
    return {"status": "ok", "deal_type": deal_type, "stored_questions": len(questions)}


@app.post("/api/v1/chat/plan")
async def chat_plan(request: Request):
    """
    Scrum Master Phase 3: Create structured task plan after clarification.
    """
    from app.core.validation.chat_guard import check_prompt

    body = await request.json()
    prompt = body.get("prompt", "")

    # guardrail: ensure prompt passes basic safety checks
    guard = check_prompt(prompt)
    if not guard["valid"]:
        return {"error": "invalid_prompt", "details": guard}

    deal_id = body.get("deal_id", "unknown")
    company_name = body.get("company_name", "Target Company")
    user_answers = body.get("user_answers", [])

    from app.agents.project_manager import ProjectManagerAgent
    from app.core.llm.model_router import get_model_router
    from app.core.llm import get_llm_client

    router = get_model_router()
    provider, _ = await router.get_provider_with_fallback("project_manager")
    llm_client = get_llm_client(provider)

    pm = ProjectManagerAgent(llm_client=llm_client)
    result = await pm.generate_plan_with_risks(
        prompt,
        context={
            "deal_id": deal_id,
            "company_name": company_name,
            "user_prompt": prompt,
            "user_answers": user_answers,
        },
    )

    return {
        "success": True,
        "reasoning": result.get("message", ""),
        "confidence": 0.9,
        "execution_time_ms": result.get("execution_time_ms", 0),
        "data": {"todo_list": result.get("todo_list", {})},
    }


@app.post("/api/v1/chat/execute-task")
async def chat_execute_task(request: Request):
    """Execute a single task from the scrum master's plan via the assigned agent."""
    from app.core.validation.chat_guard import check_prompt

    body = await request.json()
    agent_type = body.get("agent_type", "")
    task_description = body.get("task", "")

    # task description should be checked too in case it was user-generated
    guard = check_prompt(task_description)
    if not guard["valid"]:
        return {"error": "invalid_task_description", "details": guard}

    deal_id = body.get("deal_id", "")
    task_id = body.get("task_id", "")
    task_title = body.get("title", "")
    ticker = body.get("ticker", "")
    company_name = body.get("company_name", "")

    # Fallback to todo_list metadata if ticker is missing
    deal_id = body.get("deal_id")
    if not ticker and deal_id:
        from app.core.tasks.task_manager import get_task_manager

        tm = get_task_manager()
        lists = await tm.get_lists_for_deal(deal_id)
        if lists:
            # Use the most recent list
            latest_list = sorted(lists, key=lambda x: x.created_at, reverse=True)[0]
            if not ticker:
                ticker = latest_list.ticker
            if not company_name:
                company_name = latest_list.company_name

    # If unresolvable, pass company_name as the ticker hint so agents can use it for web search
    if not ticker and company_name:
        ticker = company_name

    from app.agents.base import get_agent_registry
    from app.core.llm.model_router import get_model_router
    from app.core.llm import get_llm_client

    # ── Alias map: AGENT_CAPABILITIES key → actual registered agent name ──
    AGENT_NAME_ALIASES = {
        "due_diligence_agent": "due_diligence_agent",
        "treasury_agent": "treasury_cash",
        "prospectus_agent": "prospectus_processing",
    }
    resolved_type = AGENT_NAME_ALIASES.get(agent_type, agent_type)

    try:
        router = get_model_router()
        provider, used_fallback = await router.get_provider_with_fallback(resolved_type)
        client = get_llm_client(provider)

        registry = get_agent_registry()
        agent = registry.get(resolved_type)

        if agent:
            agent.llm = client
            result = await agent.run(
                task_description,
                context={
                    "deal_id": deal_id,
                    "task_id": task_id,
                    "ticker": ticker,
                    "company_name": company_name,
                    "agent_outputs": body.get("agent_outputs", {}),
                },
            )
        else:
            # Fallback: use a generic LLM call
            response = await client.generate(
                prompt=task_description,
                system_prompt=f"You are a {agent_type.replace('_', ' ')} at an investment bank. "
                f"Provide a thorough analysis.",
            )
            result = type(
                "AgentOutput",
                (),
                {
                    "success": True,
                    "data": {"analysis": response.get("content", "")},
                    "reasoning": response.get("content", "")[:500],
                    "confidence": 0.75,
                    "execution_time_ms": 0,
                },
            )()

        return {
            "success": result.success,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
            "execution_time_ms": result.execution_time_ms,
            "data": result.data,
            "provider": provider,
            "used_fallback": used_fallback,
            "task_title": task_title,
            "task_id": task_id,
        }

    except Exception as e:
        logger.error("task_execution_error", agent=agent_type, error=str(e))
        return {
            "success": False,
            "reasoning": str(e),
            "confidence": 0.0,
            "data": {"error": str(e)},
            "provider": "none",
            "task_title": task_title,
            "task_id": task_id,
        }


# ═══════════════════════════════════════════════════════════
#  Settings API — Persist & Load frontend settings
# ═══════════════════════════════════════════════════════════


@app.get("/api/v1/settings")
async def get_settings_api():
    """Load saved settings."""
    from app.core.settings_service import SettingsService

    svc = SettingsService.get_instance()
    return svc.get_all()


@app.post("/api/v1/settings")
async def save_settings_api(request: Request):
    """Save settings and apply to running system."""
    from app.core.settings_service import SettingsService

    body = await request.json()
    svc = SettingsService.get_instance()
    updated = svc.update(body)
    return {"status": "saved", "settings": updated}


# ═══════════════════════════════════════════════════════════
#  LLM Gateway API — Usage stats + direct gateway calls
# ═══════════════════════════════════════════════════════════


@app.get("/api/v1/gateway/usage")
async def gateway_usage():
    """Get LLM gateway usage stats (RPM/TPM/cache/cost)."""
    from app.core.llm.llm_gateway import get_llm_gateway

    gw = get_llm_gateway()
    return gw.get_usage_stats()


@app.post("/api/v1/gateway/call")
async def gateway_call(request: Request):
    """Make a direct LLM call through the gateway (with rate limiting + retry)."""
    from app.core.llm.llm_gateway import get_llm_gateway

    body = await request.json()
    gw = get_llm_gateway()
    result = await gw.call(
        provider=body.get("provider", "gemini"),
        prompt=body.get("prompt", ""),
        system_prompt=body.get("system_prompt"),
        max_tokens=body.get("max_tokens", 1024),
        temperature=body.get("temperature", 0.7),
    )
    return result


@app.post("/api/v1/gateway/hybrid")
async def gateway_hybrid(request: Request):
    """Hybrid reasoning: local compress → cloud reason."""
    from app.core.llm.llm_gateway import get_llm_gateway

    body = await request.json()
    gw = get_llm_gateway()
    result = await gw.hybrid_reasoning(
        question=body.get("question", ""),
        context=body.get("context", ""),
        cloud_provider=body.get("provider", "gemini"),
    )
    return result


# ═══════════════════════════════════════════════════════════
#  Gateway Rate Limit Update
# ═══════════════════════════════════════════════════════════


@app.post("/api/v1/gateway/limits")
async def update_gateway_limits(request: Request):
    """Update rate limits for a vendor."""
    from app.core.llm.llm_gateway import get_llm_gateway, VendorLimits

    body = await request.json()
    gw = get_llm_gateway()
    vendor = body.get("vendor", "gemini")
    gw.update_vendor_limits(
        vendor,
        VendorLimits(
            max_rpm=body.get("max_rpm", 50),
            max_tpm=body.get("max_tpm", 100_000),
            max_rpd=body.get("max_rpd", 10_000),
        ),
    )
    return {"status": "updated", "vendor": vendor}


# duplicate endpoint block removed


# ═══════════════════════════════════════════════════════════
#  Models Available API — query all LLM providers for model lists
# ═══════════════════════════════════════════════════════════

import asyncio as _asyncio
import httpx as _httpx


async def _fetch_gemini_models(api_key: str) -> dict:
    """Fetch available Gemini models from Google AI API."""
    if not api_key or api_key == "***":
        return {"status": "no_key", "models": []}
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    {
                        "id": m["name"].replace("models/", ""),
                        "name": m.get("displayName", m["name"]),
                        "context_window": m.get("inputTokenLimit", 0),
                        "daily_limit": (
                            "1,500 RPD (free)"
                            if "flash" in m.get("name", "").lower()
                            else "50 RPD (free)"
                        ),
                    }
                    for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                return {"status": "online", "models": models}
            return {
                "status": "error",
                "models": [],
                "error": f"HTTP {resp.status_code}",
            }
    except Exception as e:
        return {"status": "offline", "models": [], "error": str(e)}


async def _fetch_mistral_models(api_key: str) -> dict:
    """Fetch available Mistral models."""
    if not api_key or api_key == "***":
        return {"status": "no_key", "models": []}
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                _mistral_ctx = {
                    "mistral-large": 128000,
                    "mistral-small": 128000,
                    "codestral": 256000,
                    "mistral-medium": 32000,
                }
                models = [
                    {
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "context_window": next(
                            (v for k, v in _mistral_ctx.items() if k in m["id"]), 32000
                        ),
                        "daily_limit": "Free: 1 RPM",
                    }
                    for m in data.get("data", [])
                ]
                return {"status": "online", "models": models}
            return {
                "status": "error",
                "models": [],
                "error": f"HTTP {resp.status_code}",
            }
    except Exception as e:
        return {"status": "offline", "models": [], "error": str(e)}


async def _fetch_openai_models(api_key: str) -> dict:
    """Fetch available OpenAI models."""
    if not api_key or api_key == "***":
        return {"status": "no_key", "models": []}
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                _openai_ctx = {
                    "gpt-4o": 128000,
                    "gpt-4o-mini": 128000,
                    "gpt-4-turbo": 128000,
                    "gpt-4": 8192,
                    "gpt-3.5-turbo": 16385,
                    "o1": 200000,
                    "o3": 200000,
                }
                gpt_models = [
                    {
                        "id": m["id"],
                        "name": m["id"],
                        "context_window": next(
                            (v for k, v in _openai_ctx.items() if k in m["id"]), 8192
                        ),
                        "daily_limit": "Tier 1: 500 RPM",
                    }
                    for m in data.get("data", [])
                    if "gpt" in m["id"] or "o1" in m["id"] or "o3" in m["id"]
                ]
                return {
                    "status": "online",
                    "models": sorted(gpt_models, key=lambda x: x["id"], reverse=True),
                }
            return {
                "status": "error",
                "models": [],
                "error": f"HTTP {resp.status_code}",
            }
    except Exception as e:
        return {"status": "offline", "models": [], "error": str(e)}


async def _fetch_ollama_models(base_url: str) -> dict:
    """Fetch locally-running Ollama models."""
    try:
        async with _httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    {"id": m["name"], "name": m["name"]} for m in data.get("models", [])
                ]
                return {"status": "online", "models": models}
            return {"status": "offline", "models": []}
    except Exception:
        return {"status": "offline", "models": []}


async def _fetch_lmstudio_models(base_url: str) -> dict:
    """Fetch locally-running LM Studio models."""
    try:
        async with _httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base_url}/models")
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    {"id": m["id"], "name": m.get("name", m["id"])}
                    for m in data.get("data", [])
                ]
                return {"status": "online", "models": models}
            return {"status": "offline", "models": []}
    except Exception:
        return {"status": "offline", "models": []}


@app.get("/api/v1/models/available")
async def get_available_models():
    """
    Query all configured LLM providers simultaneously and return their available models.
    This powers the Settings page model selection dropdowns.
    """
    gemini_key = _os.environ.get("GEMINI_API_KEY", "")
    openai_key = _os.environ.get("OPENAI_API_KEY", "")
    mistral_key = _os.environ.get("MISTRAL_API_KEY", "").strip()
    ollama_url = _os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    lmstudio_url = _os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")

    # Fetch all providers in parallel
    results = await _asyncio.gather(
        _fetch_gemini_models(gemini_key),
        _fetch_mistral_models(mistral_key),
        _fetch_openai_models(openai_key),
        _fetch_ollama_models(ollama_url),
        _fetch_lmstudio_models(lmstudio_url),
        return_exceptions=True,
    )

    def _safe(r, fallback_status="offline"):
        if isinstance(r, Exception):
            return {"status": fallback_status, "models": [], "error": str(r)}
        return r

    return {
        "gemini": _safe(results[0]),
        "mistral": _safe(results[1]),
        "openai": _safe(results[2]),
        "ollama": _safe(results[3]),
        "lmstudio": _safe(results[4]),
    }


@app.post("/api/v1/models/test")
async def test_cloud_model(request: Request):
    """Test a cloud API key directly from Settings UI before saving"""
    body = await request.json()
    provider = body.get("provider", "")
    api_key = body.get("api_key", "")

    if not provider or not api_key:
        return {"ok": False, "error": "provider and api_key required"}

    try:
        if provider == "gemini":
            result = await _fetch_gemini_models(api_key)
        elif provider == "openai":
            result = await _fetch_openai_models(api_key)
        elif provider == "mistral":
            result = await _fetch_mistral_models(api_key)
        else:
            return {"ok": False, "error": f"Unknown provider {provider}"}

        if result.get("status") == "online":
            return {"ok": True, "models": result.get("models", [])}
        else:
            return {
                "ok": False,
                "error": result.get("error", "API Key Invalid or rate limited"),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/v1/llm/usage")
async def llm_usage_stats():
    """
    Return live LLM usage stats: rate limits, token counts, API key health,
    and cache performance — for the frontend monitoring dashboard.
    """
    from app.core.llm.llm_gateway import get_llm_gateway

    settings = get_settings()
    gateway = get_llm_gateway()
    raw = gateway.get_usage_stats()

    # Enrich each vendor with API key status and utilization %
    api_key_map = {
        "gemini": settings.GEMINI_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "mistral": settings.MISTRAL_API_KEY,
    }

    # Known model metadata (context windows + pricing tier hints)
    model_metadata = {
        "gemini": {
            "popular_models": [
                {"id": "gemini-2.5-flash", "context": "1M", "daily_free": "1,500 RPD"},
                {"id": "gemini-2.0-flash", "context": "1M", "daily_free": "1,500 RPD"},
                {"id": "gemini-1.5-pro", "context": "2M", "daily_free": "50 RPD"},
                {"id": "gemini-1.5-flash", "context": "1M", "daily_free": "1,500 RPD"},
            ]
        },
        "openai": {
            "popular_models": [
                {"id": "gpt-4o", "context": "128K", "daily_free": "Tier 1: 500 RPM"},
                {
                    "id": "gpt-4o-mini",
                    "context": "128K",
                    "daily_free": "Tier 1: 500 RPM",
                },
                {
                    "id": "gpt-4-turbo",
                    "context": "128K",
                    "daily_free": "Tier 1: 500 RPM",
                },
                {"id": "o1", "context": "200K", "daily_free": "Tier 1: 500 RPM"},
            ]
        },
        "mistral": {
            "popular_models": [
                {
                    "id": "mistral-large-latest",
                    "context": "128K",
                    "daily_free": "Free: 1 RPM",
                },
                {
                    "id": "mistral-small-latest",
                    "context": "128K",
                    "daily_free": "Free: 1 RPM",
                },
                {
                    "id": "codestral-latest",
                    "context": "256K",
                    "daily_free": "Free: 1 RPM",
                },
            ]
        },
    }

    enriched_vendors = {}
    for vendor_name, vendor_data in raw.get("vendors", {}).items():
        key = api_key_map.get(vendor_name)
        rpm = vendor_data.get("rpm", {})
        tpm = vendor_data.get("tpm", {})
        rpd = vendor_data.get("rpd", {})

        # Utilisation percentages
        rpm_pct = round((rpm.get("current", 0) / max(rpm.get("limit", 1), 1)) * 100, 1)
        tpm_pct = round((tpm.get("current", 0) / max(tpm.get("limit", 1), 1)) * 100, 1)
        rpd_pct = round((rpd.get("current", 0) / max(rpd.get("limit", 1), 1)) * 100, 1)

        enriched_vendors[vendor_name] = {
            **vendor_data,
            "api_key_configured": bool(key),
            "api_key_masked": (
                f"{key[:4]}...{key[-4:]}"
                if key and len(key) > 8
                else ("***" if key else "")
            ),
            "rpm_pct": rpm_pct,
            "tpm_pct": tpm_pct,
            "rpd_pct": rpd_pct,
            "model_metadata": model_metadata.get(vendor_name, {}),
        }

    return {
        "vendors": enriched_vendors,
        "cache": raw.get("cache", {}),
        "recent_calls": raw.get("recent_calls", 0),
    }


# ═══════════════════════════════════════════════════════════
#  DealForge 2.0 — MCP Integration API endpoints
# ═══════════════════════════════════════════════════════════


@app.get("/api/v1/mcp/status")
@app.get("/api/v1/mcp/providers")
async def mcp_providers():
    """
    Returns the status of all registered MCP data providers, including
    runtime-configured ones (set via the Settings UI).
    """
    from app.core.mcp import get_provider_status

    return {"providers": get_provider_status()}


@app.post("/api/v1/mcp/initialize")
async def mcp_initialize(request: Request):
    """
    Initialize and live-test an MCP provider API key.
    Persists the key in the runtime store for this session.
    Body: { "provider": "finnhub", "api_key": "..." }
    """
    from app.core.mcp import initialize_provider

    body = await request.json()
    provider = body.get("provider", "")
    api_key = body.get("api_key", "")
    if not provider or not api_key:
        return {"ok": False, "error": "provider and api_key are required"}
    result = await initialize_provider(provider, api_key)
    return result


@app.post("/api/v1/mcp/search")
async def mcp_search_company(request: Request):
    """Search for a company across all configured MCP providers."""
    from app.core.mcp import get_mcp_router

    body = await request.json()
    company_name = body.get("company_name", "")
    if not company_name:
        return {"error": "company_name is required"}
    router = get_mcp_router()
    result = await router.search_company(company_name)
    return result


# ═══════════════════════════════════════════════════════════
#  Scrum Master — Reasoning, Clarification & Planning API
# ═══════════════════════════════════════════════════════════


@app.post("/api/v1/scrum/clarify")
async def scrum_clarify(request: Request):
    """
    Phase 1 + 2 of the Scrum Master workflow:
    - Identify required data/files for the task
    - Determine what can be auto-fetched via MCP vs what user must provide
    - Generate clarifying questions with visible reasoning
    Body: { "task": "...", "context": {} }
    """
    from app.agents.project_manager import ProjectManagerAgent
    from app.core.mcp import get_provider_status

    from app.core.validation.chat_guard import check_prompt

    body = await request.json()
    task = body.get("task", "")
    context = body.get("context", {})

    if not task:
        return {"error": "task is required"}

    # guardrail: simple sanity check on the task text
    guard = check_prompt(task)
    if not guard["valid"]:
        return {"error": "invalid_task", "details": guard}

    # Build MCP capability context for the agent
    mcp_status = get_provider_status()
    configured_mcps = [p for p in mcp_status if p["configured"]]
    context["available_mcp_providers"] = configured_mcps

    agent = ProjectManagerAgent()
    result = await agent.generate_clarifying_questions(task, context)
    return result


@app.post("/api/v1/scrum/plan")
async def scrum_plan(request: Request):
    """
    Phase 3 of the Scrum Master workflow:
    - Takes user answers to clarification questions
    - Generates a structured MECE todo list with risk flags per task
    - Does NOT auto-execute — returns plan for user approval
    Body: { "task": "...", "context": {}, "answers": [...], "provided_data": {} }
    """
    from app.agents.project_manager import ProjectManagerAgent
    from app.core.mcp import get_provider_status
    from app.core.validation.chat_guard import check_prompt

    body = await request.json()
    task = body.get("task", "")
    context = body.get("context", {})
    answers = body.get("answers", [])
    provided_data = body.get("provided_data", {})

    if not task:
        return {"error": "task is required"}

    guard = check_prompt(task)
    if not guard["valid"]:
        return {"error": "invalid_task", "details": guard}

    mcp_status = get_provider_status()
    context["available_mcp_providers"] = [p for p in mcp_status if p["configured"]]
    context["user_answers"] = answers
    context["provided_data"] = provided_data

    agent = ProjectManagerAgent()
    result = await agent.generate_plan_with_risks(task, context)
    return result


# ═══════════════════════════════════════════════════════════
#  DealForge 2.0 — Skills Library API endpoints
# ═══════════════════════════════════════════════════════════


@app.get("/api/v1/skills/list")
async def list_skills():
    """Return all available domain skills in the Skills Library."""
    from app.core.skills import list_available_skills, SKILL_MAP

    skills = list_available_skills()
    # Build a reverse map: filename → keywords that trigger it
    reverse_map: dict = {}
    for keyword, filename in SKILL_MAP.items():
        if filename not in reverse_map:
            reverse_map[filename] = []
        reverse_map[filename].append(keyword)
    return {
        "skill_count": len(skills),
        "skills": [
            {
                "filename": s,
                "trigger_keywords": reverse_map.get(s, [])[:5],  # Show first 5 keywords
            }
            for s in sorted(skills)
        ],
    }


# ═══════════════════════════════════════════════════════════
#  OFAS — Multi-Agent Financial Analysis Endpoints
# ═══════════════════════════════════════════════════════════

_ofas_missions: Dict[str, dict] = {}  # deal_id -> OFASMissionState


@app.get("/api/v1/ofas/templates")
async def ofas_list_templates():
    """List available OFAS deal type templates"""
    from app.agents.ofas_supervisor import DEAL_TYPE_TEMPLATES

    return {
        "templates": {
            k: {"description": v["description"], "task_count": len(v["tasks"])}
            for k, v in DEAL_TYPE_TEMPLATES.items()
        }
    }


@app.post("/api/v1/ofas/mission")
async def ofas_create_mission(request: Request):
    """Create and plan an OFAS mission"""
    body = await request.json()

    ticker = body.get("ticker", "")
    objective = body.get("objective", "")
    deal_type = body.get("deal_type", "standard_corporate")
    constraints = body.get("constraints", [])
    deal_id = body.get("deal_id", f"ofas_{ticker}_{uuid.uuid4().hex[:8]}")

    if not ticker or not objective:
        raise HTTPException(status_code=400, detail="ticker and objective are required")

    try:
        from app.agents.ofas_supervisor import OFASSupervisorAgent

        supervisor = OFASSupervisorAgent()
        result = await supervisor.run(
            task=objective,
            context={
                "action": "plan_mission",
                "ticker": ticker,
                "deal_type": deal_type,
                "deal_id": deal_id,
                "constraints": constraints,
            },
        )

        if result.success:
            mission = result.data.get("mission", {})
            _ofas_missions[deal_id] = mission
            return {
                "deal_id": deal_id,
                "status": "planned",
                "mission": mission,
                "metadata": {
                    "deal_type": deal_type,
                    "task_count": result.data.get("task_count", 0),
                    "agents_involved": result.data.get("agents_involved", []),
                    "ready_tasks": result.data.get("ready_tasks", []),
                },
            }
        else:
            raise HTTPException(
                status_code=400, detail=result.data.get("error", "Planning failed")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("OFAS mission creation failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/ofas/mission/{deal_id}/status")
async def ofas_mission_status(deal_id: str):
    """Get OFAS mission status"""
    mission = _ofas_missions.get(deal_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {deal_id} not found")

    try:
        from app.agents.ofas_supervisor import OFASSupervisorAgent

        supervisor = OFASSupervisorAgent()
        result = await supervisor.run(
            task="status",
            context={"action": "get_status", "mission": mission},
        )

        return {
            "deal_id": deal_id,
            **result.data,
        }

    except Exception as e:
        logger.error("OFAS status check failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ofas/financial-data")
async def ofas_fetch_financial_data(request: Request):
    """Fetch financial data for a ticker (SEC EDGAR + Yahoo Finance)"""
    body = await request.json()

    ticker = body.get("ticker", "")
    statements = body.get("statements", ["income", "balance", "cashflow"])
    periods = body.get("periods", 5)
    frequency = body.get("frequency", "annual")

    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    try:
        from app.core.tools.financial_data_api import FetchFinancialStatementsTool

        tool = FetchFinancialStatementsTool()
        result = tool.execute(
            ticker=ticker,
            statements=statements,
            periods=periods,
            frequency=frequency,
        )

        if result.success:
            return result.data
        else:
            raise HTTPException(status_code=404, detail=result.error)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Financial data fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase 5: OFAS Monitoring & Review Gate Endpoints ──


@app.get("/api/v1/ofas/mission/{deal_id}/monitor")
async def ofas_mission_monitor(deal_id: str):
    """Get real-time monitoring data for an OFAS mission"""
    mission = _ofas_missions.get(deal_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {deal_id} not found")

    try:
        from app.orchestrator.ofas_engine import OFASExecutionEngine

        engine = OFASExecutionEngine()
        return engine.mission_monitor(mission)

    except Exception as e:
        logger.error("OFAS monitor failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ofas/mission/{deal_id}/review-gate")
async def ofas_review_gate(deal_id: str, request: Request):
    """Evaluate a review gate checkpoint for an OFAS mission"""
    mission = _ofas_missions.get(deal_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {deal_id} not found")

    body = await request.json()
    gate_name = body.get("gate_name", "")
    human_decision = body.get("approved")

    if not gate_name:
        raise HTTPException(status_code=400, detail="gate_name is required")

    try:
        from app.orchestrator.ofas_engine import OFASExecutionEngine

        engine = OFASExecutionEngine()
        result = await engine.evaluate_review_gate(gate_name, mission, human_decision)
        return result.to_dict()

    except Exception as e:
        logger.error("OFAS review gate failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ofas/mission/{deal_id}/recover")
async def ofas_recover_blocked(deal_id: str):
    """Attempt to recover blocked tasks in an OFAS mission"""
    mission = _ofas_missions.get(deal_id)
    if not mission:
        raise HTTPException(status_code=404, detail=f"Mission {deal_id} not found")

    try:
        from app.orchestrator.ofas_engine import OFASExecutionEngine

        engine = OFASExecutionEngine()
        updated = await engine.recover_blocked_tasks(mission, {})
        _ofas_missions[deal_id] = updated

        return {
            "deal_id": deal_id,
            "status": "recovery_attempted",
            "blocked_remaining": sum(
                1 for t in updated.get("tasks", []) if t["status"] == "blocked"
            ),
        }

    except Exception as e:
        logger.error("OFAS recovery failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ===== Main Entry Point =====


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
