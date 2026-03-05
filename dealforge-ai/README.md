# DealForge AI

A multi-agent M&A simulation workspace powered by LangGraph, PageIndex, and OpenAI Codex.

![DealForge AI](https://img.shields.io/badge/DealForge-AI-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green)
![React](https://img.shields.io/badge/React-18-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.0.48-orange)

## Features

- **Multi-Agent System**: Specialized agents for financial analysis, legal review, risk assessment, and market research
- **LangGraph Orchestration**: Structured workflow management with state machines
- **PageIndex RAG**: Document retrieval and knowledge management
- **Deal Scoring Engine**: Multi-factor scoring with risk assessment
- **Reflection & RL**: Self-improving agents with reward-based optimization
- **Real-time Dashboard**: WebSocket-powered live updates
- **Codex Integration**: Automated code generation and workspace evolution

## Architecture

```
User → React Dashboard
     ↓
FastAPI Backend
     ↓
LangGraph Orchestrator
     ↓
Agents (Gemini/Mistral Models)
     ↓
PageIndex / Tools / Codex Engine
     ↓
PostgreSQL + Redis
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose (optional)
- PostgreSQL 15+
- Redis 7+

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/dealforge-ai.git
cd dealforge-ai
```

2. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Run with Docker Compose**
```bash
docker-compose up -d
```

Or run locally:

4. **Backend setup**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

5. **Frontend setup**
```bash
cd frontend
npm install
npm run dev
```

6. **Access the application**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## API Endpoints

### Deals
- `POST /api/v1/deals` - Create a new deal
- `POST /api/v1/deals/{deal_id}/run` - Run deal workflow
- `GET /api/v1/deals/{deal_id}/status` - Get deal status
- `GET /api/v1/deals/{deal_id}/results` - Get deal results

### Agents
- `GET /api/v1/agents` - List available agents
- `POST /api/v1/agents/run` - Run a specific agent

### Documents
- `POST /api/v1/documents/upload` - Upload and index document
- `POST /api/v1/documents/query` - Query indexed documents

### Scoring
- `POST /api/v1/scoring/calculate` - Calculate deal score

### Codex
- `POST /api/v1/codex/generate` - Generate code with Codex

## Agent Types

| Agent | Description |
|-------|-------------|
| `financial_analyst` | Financial modeling and valuation |
| `legal_advisor` | Legal document review and risk assessment |
| `risk_assessor` | Business and operational risk analysis |
| `market_researcher` | Market sizing and competitive analysis |
| `debate_moderator` | Synthesizes agent perspectives |
| `scoring_agent` | Calculates final deal scores |

## Workflow Stages

1. **Init** - Initialize workflow
2. **Screening** - Initial market assessment
3. **Due Diligence** - Parallel agent analysis
4. **Debate** - Synthesize conflicting viewpoints
5. **Scoring** - Calculate final deal score
6. **Decision** - Generate recommendation

## Deal Scoring

The scoring engine evaluates deals across 6 dimensions:

| Component | Weight | Description |
|-----------|--------|-------------|
| Market | 20% | TAM, growth rate, competition |
| Team | 15% | Experience, completeness, retention |
| Traction | 20% | Revenue growth, retention, unit economics |
| Financials | 20% | Margins, cash flow, path to profitability |
| Risk | 15% | Legal, regulatory, operational risks |
| Strategic Fit | 10% | Synergies, cultural alignment |

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `MISTRAL_API_KEY` | Mistral API key | Optional |
| `GEMINI_API_KEY` | Gemini API key | Optional |
| `PAGEINDEX_API_KEY` | VectifyAI PageIndex key | Optional |
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `REDIS_URL` | Redis connection | Yes |

### Workflow Configuration

```python
config = {
    "max_iterations": 10,
    "timeout_seconds": 300,
    "parallel_execution": True,
    "enable_reflection": True,
    "reflection_threshold": 0.6,
    "require_human_approval": False,
}
```

## Development

### Backend Structure
```
backend/app/
├── api/           # API endpoints
├── agents/        # Agent implementations
├── orchestrator/  # LangGraph workflow
├── core/          # Core services
│   ├── memory/    # PageIndex client
│   ├── llm/       # LLM clients
│   ├── tools/     # Tool router
│   ├── reflection/# Reflection engine
│   └── scoring/   # Deal scorer
└── db/            # Database models
```

### Frontend Structure
```
frontend/src/
├── sections/      # Page sections
│   ├── Dashboard.tsx
│   ├── DealDetail.tsx
│   └── CreateDealDialog.tsx
├── hooks/         # Custom hooks
├── types/         # TypeScript types
└── components/ui/ # shadcn/ui components
```

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## Deployment

### Production Build

```bash
# Build frontend
cd frontend
npm run build

# Build backend Docker image
cd ../backend
docker build -t dealforge-backend .

# Deploy with docker-compose
docker-compose -f docker-compose.yml up -d
```

### Kubernetes (Optional)

```bash
kubectl apply -f infra/k8s/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - see LICENSE file for details

## Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) for workflow orchestration
- [PageIndex](https://vectify.ai) for document RAG
- [OpenAI Codex](https://openai.com/codex) for code generation
- [FastAPI](https://fastapi.tiangolo.com) for the backend framework
- [shadcn/ui](https://ui.shadcn.com) for UI components
