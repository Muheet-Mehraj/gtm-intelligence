# GTM Intelligence

> Multi-agent outbound intelligence engine. Takes a natural language ICP query and returns enriched, scored target accounts with personalized GTM strategy.

---

## Architecture

```
Query
  │
  ▼
┌──────────┐     ┌───────────┐     ┌─────────────┐     ┌────────┐     ┌──────────────┐
│  Planner │────▶│ Retrieval │────▶│ Enrichment  │────▶│ Critic │────▶│ GTM Strategy │
└──────────┘     └───────────┘     └─────────────┘     └────────┘     └──────────────┘
     ▲                                                       │
     │                    RETRY (critic feedback)            │
     └───────────────────────────────────────────────────────┘
```

All agents share a central `AgentState` object. The Critic can reject results and feed structured feedback back to the Planner, which adjusts its plan and re-runs the pipeline (up to 3 retries).

---

## Key Features

### Multi-Agent Orchestration
Five specialized agents with clear separation of concerns:
- **Planner** — converts natural language query into a structured execution plan (`entity_type`, `filters`, `tasks`, `strategy`, `confidence`)
- **Retrieval** — fetches and scores candidate companies from data sources using industry + region + keyword matching with soft fallback
- **Enrichment** — computes ICP scores, buying signals, insights, and `why_this_result` explanations
- **Critic** — validates results for relevance, hallucinations, region/industry mismatch, quality, and signal presence
- **GTM Strategy** — generates personalized email hooks, multi-persona messaging, and competitive positioning

### Retry Loop with Critic Feedback
The Critic returns `PASS | RETRY | FAIL`. On `RETRY`, the reason is stored in `state.memory["critic_feedback"]` and passed back to the Planner, which adjusts region, industry, or search scope. The full reasoning trace is preserved across retries.

### Memory System
- **SessionMemory** — TTL-based exact query cache (5 min). Repeat queries return instantly.
- **VectorStore** — keyword-similarity store of past query→results pairs. Similar future queries are augmented with relevant past records and signals.

### ICP Scoring Engine
Multi-factor scoring in `enrichment.py`:
- Signal weights (growth_funding, hiring_aggressively, mid_market_growth, etc.)
- Employee band scoring
- Funding stage scoring
- Apollo intent score boost
- Explorium GTM fit boost
- Churn risk adjustment

### Buying Signal Detection
Signals detected per company: `growth_funding`, `mid_market_growth`, `enterprise_scale`, `early_stage_team`, `hiring_aggressively`, `churn_risk`, `late_stage`.

### Multi-Persona Targeting
GTM Strategy agent generates tailored messaging for VP Sales, CEO, and CTO — each with persona-specific pain points, value props, hooks, and CTAs.

### Competitive Intelligence
Per-company competitive stack inference and positioning strategy based on industry and signals.

### Streaming via WebSocket
The frontend connects to `ws://localhost:8000/ws/run` and receives live `agent_update` events as each pipeline step completes, with real-time timeline updates in the UI.

---

## Failure Handling

| Failure Mode | Response |
|---|---|
| Empty retrieval | Soft fallback → industry/region soft match → diverse sample |
| Critic RETRY | Planner re-plans with feedback; up to 3 attempts |
| Critic FAIL | Hard stop, return errors |
| Enrichment exception | Skip record, continue |
| GTM exception | Return empty strategy, surface error |
| Critic crash | Default to PASS, log warning |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python |
| WebSocket | FastAPI WebSocket |
| Rate Limiting | slowapi |
| Frontend | React + TypeScript + Vite |
| Memory | In-memory TTL cache + keyword vector store |
| Observability | Structured logging + reasoning trace + span tracer |

---

## Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:8000`  
Frontend runs on `http://localhost:5173`

---

## API

### POST `/run`
Rate limited: 20 requests/minute

```json
{ "query": "Find high-growth AI SaaS companies in the US" }
```

### WebSocket `/ws/run`
Send: `{ "query": "..." }`  
Receive: stream of `agent_update` events + final `result`

---

## Observability

Every pipeline run produces:
- `reasoning_trace` — human-readable log of every agent decision
- `spans` — structured tracer events per agent
- `errors` — accumulated error list
- `retry_count` — number of critic-triggered replanning cycles
- `confidence` — final pipeline confidence score (0.0–1.0)
