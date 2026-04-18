# GTM Intelligence

> Multi-agent outbound intelligence engine that converts a natural language ICP query into enriched, scored target accounts with personalized GTM strategy.
> Designed to simulate how GTM teams identify, validate, and target high-value accounts.

---

## What this does

Given a natural language ICP query, this system:

* Identifies high-fit target companies using multi-source retrieval
* Enriches profiles with buying signals, intent data, and ICP scoring
* Validates results using a Critic agent to eliminate hallucinations and mismatches
* Generates personalized outbound GTM strategies tailored to specific personas

All steps execute through a multi-agent pipeline with autonomous retry loops and real-time WebSocket streaming.

---

## Architecture

```text
Query
  │
  ▼
┌──────────┐     ┌───────────┐     ┌─────────────┐     ┌────────┐     ┌──────────────┐
│  Planner │────▶│ Retrieval │────▶│ Enrichment  │────▶│ Critic │────▶│ GTM Strategy │
└──────────┘     └───────────┘     └─────────────┘     └────────┘     └──────────────┘
     ▲                                                         │
     │                   RETRY (critic feedback)               │
     └─────────────────────────────────────────────────────────┘
```

All agents share a central `AgentState` object. The Critic can reject results and provide structured feedback to the Planner, which adjusts the execution plan and re-runs the pipeline (up to three retries).

---

## Why this is different

Unlike traditional linear enrichment pipelines:

* **Autonomous correction** — The Critic agent validates outputs and triggers retries when necessary
* **Explainability** — Maintains a reasoning trace across all agent decisions
* **End-to-end execution** — Retrieval, enrichment, validation, and GTM strategy generation in a unified pipeline
* **Real-time visibility** — Streams intermediate agent updates via WebSocket

---

## Example

**Query**
`"Identify fintech startups hiring aggressively in the US"`

**Output includes**

* **Company:** Rippling
* **Signals:** enterprise_scale, hiring_aggressively, growth_funding
* **Insight:** Scaling team post-Series F with strong outbound potential
* **Why:** High headcount growth, funding stage, and intent signals
* **GTM Strategy:** Persona-specific outreach for VP Sales, CEO, and CTO

---

## System Capabilities

### Multi-Agent Orchestration

* **Planner** — Converts natural language into a structured execution plan
* **Retrieval** — Fetches candidate companies using industry, region, and keyword matching
* **Enrichment** — Computes ICP scores, signals, insights, and `why_this_result`
* **Critic** — Validates relevance, hallucinations, and output quality
* **GTM Strategy** — Generates personalized messaging and positioning

---

### Retry Loop with Critic Feedback

* Critic returns: `PASS | RETRY | FAIL`
* On `RETRY`, feedback is stored in `state.memory["critic_feedback"]`
* Planner adjusts filters (region, industry, scope) and retries
* Maximum of three retries with full reasoning trace preserved

---

### Memory System

* **SessionMemory** — TTL-based cache (5 minutes) for repeated queries
* **VectorStore** — Similarity-based retrieval of past query-result pairs

---

### ICP Scoring Engine

Multi-factor scoring includes:

* Signal weighting (growth, hiring, funding)
* Employee band scoring
* Funding stage scoring
* Intent signals (Apollo, Explorium)
* Churn risk adjustments

---

### Buying Signal Detection

Signals detected per company:

* growth_funding
* hiring_aggressively
* enterprise_scale
* mid_market_growth
* early_stage_team
* churn_risk
* late_stage

---

### Multi-Persona Targeting

Generates tailored messaging for:

* VP Sales
* CEO
* CTO

Each persona includes specific pain points, value propositions, and call-to-action strategies.

---

### Competitive Intelligence

Infers competitive stack and generates positioning strategy based on industry and detected signals.

---

### Streaming via WebSocket

Frontend connects to:

```
ws://localhost:8000/ws/run
```

Streams:

* Agent updates
* Reasoning steps
* Final results

---

## Failure Handling

| Failure Mode     | Response                       |
| ---------------- | ------------------------------ |
| Empty retrieval  | Soft fallback to broader match |
| Critic RETRY     | Planner re-runs with feedback  |
| Critic FAIL      | Hard stop with error           |
| Enrichment error | Skip record and continue       |
| GTM error        | Return partial result          |
| Critic crash     | Default to PASS                |

---

## Tech Stack

| Layer         | Technology                |
| ------------- | ------------------------- |
| Backend       | FastAPI + Python          |
| Streaming     | WebSocket                 |
| Frontend      | React + TypeScript + Vite |
| Memory        | TTL Cache + Vector Store  |
| Observability | Logging + Reasoning Trace |

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

* Backend: http://localhost:8000
* Frontend: http://localhost:5173

---

## API

### POST `/run`

```json
{ "query": "Find high-growth AI SaaS companies in the US" }
```

---

### WebSocket `/ws/run`

Send:

```json
{ "query": "..." }
```

Receive:

* `agent_update` events
* Final `result`

---

## Observability

Each run produces:

* `reasoning_trace` — step-by-step agent decisions
* `spans` — structured tracing events
* `errors` — accumulated failures
* `retry_count` — number of retries
* `confidence` — final pipeline confidence score (0.0–1.0)

---
