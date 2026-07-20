# VeeTrack

AI-powered media intelligence platform. A Flipboard-style story feed for PR and executive teams —
ingests news, social, RSS, and YouTube; clusters content into stories; and generates AI executive
briefs and PR recommendations. Designed to replace spreadsheet dashboards (Meltwater, Brandwatch)
with a TikTok-style vertical swipe UI.

## Architecture Overview

```
apps/web       Next.js 15 (App Router, TypeScript, Tailwind, dark-mode-first)
apps/api       FastAPI (Clean Architecture, async, JWT + RBAC)
apps/workers   Celery (4 queues: ingestion | nlp | llm | alerts)
infra/         Docker Compose (Postgres+pgvector, Redis), Dockerfiles, future K8s
packages/      shared-types (TypeScript)
```

**AI Pipeline** (always async, never triggered at request time):
Source connectors → Normalizer → Dedup (MinHash) → Entity extraction (GLiNER) →
Embeddings (BGE → pgvector) → Clustering (HDBSCAN) → Sentiment (ModernBERT) →
Executive Brief (Claude hosted) → Recommendations (confidence-gated) → Alerts

**Search:** Fast Path (precomputed, served from Redis) / Cold Path (pgvector similarity, then
auto-promotes to tracked).

## Prerequisites

- Docker + Docker Compose
- Node.js 20+ and pnpm (`npm install -g pnpm`)
- Python 3.11+ and uv (`pip install uv`)

## Local Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> veetrack && cd veetrack

# 2. Copy and fill in secrets
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, JWT_SECRET, and any API keys you have

# 3. Start infrastructure
docker compose -f infra/docker-compose.yml --env-file .env up -d

# 4. Install frontend deps (from repo root)
pnpm install
```

## Running Each App

**Frontend:**
```bash
pnpm --filter web dev          # http://localhost:3000
```

**API:**
```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000
# GET /health → {"status": "ok"}
```

**Workers:**
```bash
cd apps/workers
uv sync
uv run celery -A celery_app worker --loglevel=info -Q ingestion,nlp,llm,alerts
```

## Running Tests

```bash
# API tests
cd apps/api && uv run pytest

# Frontend tests
pnpm --filter web test
```

## Implementation Phases

28 phases, each in `docs/phases/`. Phase N+1 begins only after Phase N is confirmed complete.
See `docs/01_ARCHITECTURE.md` for the full roadmap.
