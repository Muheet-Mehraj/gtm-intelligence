# GTM Intelligence

> Multi-agent outbound intelligence engine. Takes a natural language ICP query and returns enriched, scored target accounts with personalized GTM strategy.

## What this does

Given a natural language ICP query, this system:

- Identifies high-fit target companies
- Enriches them with buying signals and intent data
- Validates results using a Critic agent (prevents hallucinations)
- Generates personalized outbound GTM strategy per company

All steps run through a multi-agent pipeline with retry loops and real-time streaming.

---

## Architecture

```text
Query
  │
  ▼
┌──────────┐     ┌───────────┐     ┌─────────────┐     ┌────────┐     ┌──────────────┐
│  Planner │────▶│ Retrieval │────▶│ Enrichment  │────▶│ Critic │────▶│ GTM Strategy │
└──────────┘     └───────────┘     └─────────────┘     └────────┘     └──────────────┘
     ▲                                                       │
     │                    RETRY (critic feedback)            │
     └───────────────────────────────────────────────────────┘
