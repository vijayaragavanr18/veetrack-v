# VeeTrack — Software Architecture Document
### Chief Architect Review, Improvements & Production Blueprint

---

## 1. Architectural Review Summary

Your vision is sound and genuinely differentiated — a Flipboard-style AI story feed instead of a
dashboard is a real UX advantage over Meltwater/Signal AI/Brandwatch, which are all spreadsheet-brained.
The core engineering risk is not the UI. It's guaranteeing **instant search over expensive AI work**.
Everything below is designed around solving that tension correctly, plus closing gaps that would bite
you in production.

### 1.1 Key Improvements Made to Your Design

| Area | Your Spec | Change / Addition | Why |
|---|---|---|---|
| Search | "search never triggers AI, always instant" | Split into **Fast Path** (tracked keywords, fully precomputed) and **Cold Path** (untracked keyword — instant retrieval-only results, no LLM call, auto-promotes to tracked + upgrades in background) | An arbitrary ad-hoc search *cannot* be precomputed. Without this split, first-time searches would either be slow or return nothing. |
| Clustering | HDBSCAN | HDBSCAN for **periodic full re-clustering** (nightly) + **incremental nearest-centroid assignment** for real-time story updates | Re-running HDBSCAN over the whole corpus on every new article does not scale past a few thousand stories. |
| AI Models | vLLM + Qwen3 4B for everything | Qwen3 4B (local, quantized AWQ/4-bit) for NER post-processing, sentiment adjudication, cheap classification. **Hosted LLM API (Claude Haiku/Sonnet)** for executive summaries, "why it happened," and recommendations | Your 8GB VRAM card cannot run vLLM + GLiNER + BGE + ModernBERT concurrently at good quality/latency. Reserve local GPU for high-volume/cheap tasks; reserve the highest-quality model for the highest-value, lowest-volume output (the exec insight is the entire product). |
| Recommendation Engine | AI-generated actions | Add **confidence gating**: recommendations below a threshold are hidden or flagged "needs human review"; every recommendation stores its reasoning trace | This is advisory content served to PR/exec users. Ungated hallucinated "risk levels" are a liability. |
| Data Sources | NewsData.io, TwitterAPI.io, RSS, YouTube Transcript | Wrap every source behind a common `SourceConnector` interface (Repository pattern) with per-source rate-limit budgets, backoff, and circuit breaker | A banned/quota-exhausted API should degrade one source, not break ingestion. |
| Entities | Implicit | Add an **Entity Resolution table**: canonical entity ("Tesla, Inc.") ↔ aliases ("Tesla", "$TSLA", "@Tesla") | Without this, "Tesla" and "$TSLA" become two different story clusters. |
| Multi-tenancy | Not specified | Add **Workspaces** with RBAC from Phase 1 (even if only one workspace exists initially) | Retrofitting multi-tenancy into a live schema is expensive; modeling it now costs almost nothing. |
| Observability | Not specified | Structured logging, Sentry, Prometheus/Grafana on Celery workers, per-LLM-call token/cost logging | You will burn API/GPU budget silently otherwise, and debugging async pipelines without tracing is painful. |
| Delivery | Web app only | Same, but architect the API as **channel-agnostic** (REST + WebSocket) so a Capacitor mobile wrapper (already in your roadmap) needs zero backend changes | Confirmed compatible with your stated plan. |

### 1.2 Additional Enterprise Features (recommended, not in original spec)

- **Watchlists & Alerts** — saved keyword sets per user/workspace, push notifications via WebSocket + email/Slack/Teams webhook on breaking/high-risk stories.
- **Executive Brief Export** — one-click PDF/PPT digest of top stories for a keyword over a time window (daily/weekly digest email).
- **Source Credibility Scoring** — static + learned score per publisher, surfaced on Page 1.
- **Competitor Benchmarking View** — side-by-side sentiment/volume trend for a set of tracked competitors.
- **Audit Trail** — who viewed/exported/acted on which story (compliance requirement for PR/legal teams).
- **Admin Console** — API quota usage per source, worker health, model latency dashboards.
- **Multi-language ingestion** — language-detect early in the pipeline; translate only what's clustered as relevant (cost control).

### 1.3 Risks Called Out Explicitly

1. **GPU contention** under concurrent embedding + NER + LLM load — mitigated via model routing/queueing (Section 4) and hosted fallback.
2. **API quota exhaustion** (NewsData.io, TwitterAPI.io free/low tiers) — mitigated via per-source token-bucket rate limiting and graceful degradation.
3. **Cold-start clustering quality** — first few days of data will produce noisy clusters; HDBSCAN parameters need tuning against a seeded historical corpus before launch.
4. **Recommendation liability** — mitigated via confidence gating + human-in-loop flag + audit trail (never auto-send an action, only ever *recommend*).

---

## 2. AI Pipeline (Revised)

```
Source Connectors (NewsData.io / TwitterAPI.io / RSS / YouTube Transcript)
        │  (per-source rate-limited pull, via Watcher Agent)
        ▼
Raw Ingestion Queue (Redis + Celery)
        ▼
Normalizer Agent        — schema unification, HTML cleanup, language detection
        ▼
Deduplication           — Datasketch MinHash/LSH near-duplicate detection
        ▼
Entity Agent            — GLiNER extraction → Entity Resolution (alias → canonical entity)
        ▼
Embedding Agent         — BGE embeddings → pgvector
        ▼
Story Clustering Agent  — incremental nearest-centroid assignment to existing story clusters
        │                 (nightly HDBSCAN full re-cluster + merge/split reconciliation)
        ▼
Sentiment Agent         — ModernBERT sentiment, per-article + cluster-aggregated
        ▼
Timeline Agent          — orders cluster articles chronologically, detects "story evolution" events
        ▼
Executive Brief Agent   — hosted LLM (Claude) generates "What Happened" / "Why It Happened"
        ▼
Recommendation Agent    — hosted LLM (Claude) generates actions + risk + confidence score
        │                 (confidence < threshold → flagged for human review, hidden from default view)
        ▼
Alert Agent             — evaluates against user watchlists, triggers WebSocket/email/Slack push
        ▼
Postgres (source of truth) + Redis (hot cache of ready-to-serve story payloads)
        ▼
Search / Feed API  ← always reads from cache/materialized tables, NEVER triggers the pipeline above
```

**Cold Path (untracked keyword searched for the first time):**
`Search API → pgvector similarity + Postgres full-text fallback (no LLM) → instant raw results
→ async: enqueue keyword as a new watched entity → full pipeline runs in background → next search is Fast Path.`

---

## 3. Backend Architecture

- **Framework:** FastAPI, versioned `/api/v1`, async endpoints throughout.
- **Pattern:** Clean Architecture — `domain` (entities, interfaces) → `application` (use cases/services) →
  `infrastructure` (DB, external APIs, Celery) → `api` (routers, schemas). No business logic in routers.
- **Repository Pattern:** every DB table and every external data source behind an interface, so
  Postgres or NewsData.io can be swapped/mocked without touching business logic.
- **Dependency Injection:** FastAPI's `Depends` graph wired via a composition root (`app/core/container.py`).
- **Background Workers:** Celery with separate queues per pipeline stage (`ingestion`, `nlp`, `llm`,
  `alerts`) so a slow LLM call never blocks cheap NER jobs. Celery Beat for scheduled pulls + nightly
  re-clustering.
- **Model Serving:** vLLM server process for local Qwen3 4B (AWQ quantized), accessed via internal HTTP —
  isolates GPU memory management from the API/worker processes. Hosted LLM calls (executive summary,
  recommendations) go through a thin `LLMGateway` abstraction so you can swap providers later.
- **Auth:** JWT access + refresh tokens, workspace-scoped RBAC (`owner`, `admin`, `analyst`, `viewer`).
- **Rate Limiting:** `slowapi`/Redis token bucket on public API + per-source token bucket for outbound
  connector calls.

---

## 4. Frontend Architecture

- **Framework:** Next.js (App Router) + TypeScript, feature-based folder structure (not type-based).
- **State:** Zustand for swipe/navigation/UI state (current story index, current page 1-4, gesture state);
  TanStack Query for all server data (stories, clusters, insights) with cache-first strategy tuned for
  the Fast Path's already-instant backend.
- **Motion:** Framer Motion for the vertical (story) and horizontal (page) swipe transitions —
  spring physics tuned to feel like TikTok, not a slideshow.
- **Gestures:** `react-swipeable` wrapping a virtualized story list (only render current ± 1 story to
  hit 60fps).
- **Design system:** shadcn/ui + Tailwind, dark-mode-first (media intelligence tools are used in
  war-room/monitoring contexts).
- **Images:** Next/Image with a CDN-backed cache (see Section 6) — hero images are the single biggest
  perf risk for 60fps scroll.

---

## 5. Folder Structure (Monorepo)

```
veetrack/
├── apps/
│   ├── web/                      # Next.js frontend
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   ├── (feed)/
│   │   │   │   ├── feed/page.tsx
│   │   │   │   └── story/[id]/page.tsx
│   │   │   └── (admin)/
│   │   ├── components/
│   │   │   ├── story-card/
│   │   │   ├── pages/             # Page1..Page4 components
│   │   │   └── ui/                 # shadcn primitives
│   │   ├── features/
│   │   │   ├── feed/               # hooks, api, store
│   │   │   ├── watchlists/
│   │   │   └── alerts/
│   │   ├── lib/
│   │   └── store/
│   │
│   ├── api/                      # FastAPI backend
│   │   ├── app/
│   │   │   ├── domain/            # entities, value objects, interfaces
│   │   │   ├── application/       # use cases / services
│   │   │   ├── infrastructure/
│   │   │   │   ├── db/            # SQLAlchemy models, repositories
│   │   │   │   ├── connectors/    # NewsDataConnector, TwitterConnector, RSSConnector, YouTubeConnector
│   │   │   │   ├── llm/           # LLMGateway, vLLM client, hosted client
│   │   │   │   └── cache/         # Redis client
│   │   │   ├── api/
│   │   │   │   └── v1/            # routers, schemas (Pydantic)
│   │   │   └── core/               # config, container (DI), security
│   │   ├── alembic/
│   │   └── tests/
│   │
│   └── workers/                  # Celery workers + beat schedule
│       ├── tasks/
│       │   ├── ingestion/
│       │   ├── nlp/                # entity, sentiment, embedding, clustering
│       │   ├── llm/                 # summary, recommendation
│       │   └── alerts/
│       └── celery_app.py
│
├── packages/
│   └── shared-types/              # OpenAPI-generated / hand-shared TS types
│
├── infra/
│   ├── docker/
│   ├── docker-compose.yml
│   └── k8s/                       # future cloud deployment
│
└── docs/
    ├── 01_ARCHITECTURE.md         # this file
    └── phases/                     # one Claude Code prompt per phase
```

---

## 6. Database Architecture (Core Tables)

```
workspaces(id, name, plan, created_at)
users(id, workspace_id FK, email, role, hashed_password, created_at)

sources(id, type[newsdata|twitter|rss|youtube], config_json, is_active, rate_limit_budget)

entities(id, canonical_name, type[company|person|topic], metadata_json)
entity_aliases(id, entity_id FK, alias_text, alias_type[name|ticker|handle])

articles(id, source_id FK, external_id, url, headline, hero_image_url, publisher,
         published_at, raw_content, clean_content, language, sentiment_label,
         sentiment_score, embedding vector(1024), dedup_hash, ingested_at)

article_entities(article_id FK, entity_id FK, relevance_score)

stories(id, primary_entity_id FK, title, status[active|resolved|archived],
        cluster_centroid vector(1024), risk_level, created_at, updated_at)

story_articles(story_id FK, article_id FK, added_at)

story_insights(id, story_id FK, what_happened, why_happened, generated_at,
               model_used, token_cost)

story_recommendations(id, story_id FK, recommendation_text, audience[pr|exec|marketing],
                       risk_level, confidence_score, needs_human_review, generated_at)

watchlists(id, workspace_id FK, user_id FK, entity_id FK, alert_channels_json)
alerts(id, watchlist_id FK, story_id FK, sent_at, channel, status)

audit_log(id, workspace_id FK, user_id FK, action, resource_type, resource_id, created_at)
api_usage_log(id, source_id FK, calls_made, quota_limit, window_start)
```

Indexes: `pgvector` HNSW/IVFFlat index on `articles.embedding` and `stories.cluster_centroid`;
GIN trigram index on `articles.headline`/`clean_content` for cold-path full-text fallback;
composite index on `entity_aliases(alias_text)` for O(1) keyword → entity resolution.

---

## 7. API Architecture

```
POST   /api/v1/auth/login | refresh
GET    /api/v1/feed?entity=Tesla&cursor=...          # Fast/Cold path search, returns Page-1 payloads
GET    /api/v1/stories/{id}                            # full 4-page payload
GET    /api/v1/stories/{id}/cluster                    # Page 3 data
GET    /api/v1/stories/{id}/recommendations             # Page 4 data
POST   /api/v1/watchlists | GET /api/v1/watchlists
POST   /api/v1/exports/brief                            # PDF/PPT executive brief
WS     /api/v1/ws/alerts                                # live push
GET    /api/v1/admin/sources/usage                       # quota dashboard
```

All list endpoints are cursor-paginated and served from Redis-cached, precomputed payloads — never
computed at request time.

---

## 8. Implementation Roadmap (Phased)

Phases follow your original 28-phase list, lightly regrouped. **One module per Claude Code prompt.
Phase N+1 is only generated after Phase N is confirmed complete.**

1. Repository & Monorepo Setup
2. Next.js Frontend Foundation
3. FastAPI Backend Foundation
4. PostgreSQL Database + pgvector
5. Redis Cache & Celery Setup
6. Authentication & Workspaces/RBAC
7. Source Connector Interface + NewsData.io Integration
8. TwitterAPI.io Integration
9. RSS Integration
10. YouTube Transcript Integration
11. Unified Ingestion Pipeline (Normalizer + Dedup)
12. Entity Recognition + Entity Resolution
13. Sentiment Analysis
14. Embedding Pipeline
15. Story Clustering (incremental + nightly HDBSCAN)
16. LLM Gateway (local vLLM + hosted) + Executive Summary Agent
17. Recommendation Engine + Confidence Gating
18. Search/Feed API (Fast Path + Cold Path)
19. Flipboard Card UI (vertical swipe shell)
20. Page 1 — Original Story UI
21. Page 2 — AI Insight UI
22. Page 3 — Story Cluster / Timeline UI
23. Page 4 — Recommendations UI
24. Watchlists + WebSocket Alerts
25. Executive Brief Export (PDF/PPT)
26. Admin Console & Observability (Sentry, Prometheus, quota dashboards)
27. Performance Optimization (60fps audit, caching, image pipeline)
28. Testing (unit/integration/e2e) & Deployment (Docker/K8s)

---

## 9. Suggested Technology Additions

- **Docker Compose** for local dev parity across both developer machines (RTX 5050 / RTX 4060).
- **uv or Poetry** for Python dependency management; **ruff + mypy** for linting/typing; **pytest**.
- **pnpm + Turborepo** for the monorepo/frontend build.
- **Meilisearch or Postgres trigram** as cold-path text fallback alongside pgvector.
- **MinIO/S3-compatible storage** for cached hero images.
- **Sentry** (error tracking) + **Prometheus/Grafana** (worker + latency metrics).
- **GitHub Actions** CI: lint, type-check, test, build on every PR.