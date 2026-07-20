# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Infrastructure

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d    # Start Postgres (pgvector) + Redis
docker compose -f infra/docker-compose.yml --env-file .env down -v  # Tear down + remove volumes
```

### Frontend (`apps/web`)

```bash
pnpm install                         # Install all workspace deps (run from repo root)
pnpm --filter web dev                # Dev server → http://localhost:3000
pnpm --filter web build              # Production build
pnpm --filter web lint               # ESLint
pnpm --filter web typecheck          # tsc --noEmit
pnpm --filter web test               # Jest + React Testing Library
pnpm --filter web test -- --testPathPattern=StoryCard  # Single test file
```

### API (`apps/api`)

```bash
cd apps/api
uv sync                                              # Install deps (including dev)
uv run uvicorn app.main:app --reload                 # Dev server → http://localhost:8000
uv run pytest                                        # All tests
uv run pytest tests/unit/test_health.py              # Single test file
uv run pytest tests/test_health.py::test_health_ok  # Single test
uv run pytest -m "not integration"                   # Skip integration tests (require live Redis)
uv run ruff check .                                  # Lint
uv run ruff format .                                 # Format
uv run mypy app/                                     # Type check
```

### Workers (`apps/workers`)

```bash
cd apps/workers
uv sync
uv run celery -A celery_app worker --loglevel=info -Q ingestion,nlp,llm,alerts
uv run celery -A celery_app beat --loglevel=info    # Scheduled tasks
```

### Monorepo (turbo)

```bash
pnpm run build     # Build all apps via Turborepo
pnpm run lint      # Lint all apps
pnpm run typecheck # Type-check all apps
```

## Architecture

VeeTrack is an AI-powered media intelligence platform — a Flipboard-style story feed for PR/exec teams. It ingests news/social/RSS/YouTube, clusters content into stories, and generates AI executive briefs and PR recommendations.

### Monorepo layout

- **`apps/web`** — Next.js 15, App Router, TypeScript, Tailwind (dark-mode-first)
- **`apps/api`** — FastAPI, Clean Architecture, fully async
- **`apps/workers`** — Celery with four queues: `ingestion`, `nlp`, `llm`, `alerts`
- **`packages/shared-types`** — shared TypeScript types (`@veetrack/shared-types`), no build step; `main`/`types` point directly to `src/index.ts`
- **`infra/`** — Docker Compose (Postgres+pgvector, Redis only), Dockerfiles, `k8s/` (empty)

`pnpm-workspace.yaml` includes only `apps/web` and `packages/*`. The API and workers are Python-only and manage their own envs via `uv`.

### Backend — Clean Architecture

`apps/api/app/` is strictly layered; dependencies only flow inward:

| Layer | Path | Responsibility |
|---|---|---|
| `domain/` | entities, value objects, interfaces | No external imports allowed |
| `application/` | use cases, services | Depends only on `domain` |
| `infrastructure/` | SQLAlchemy, Redis, LLM gateway, connectors | Implements domain interfaces |
| `api/v1/` | FastAPI routers, Pydantic schemas | Calls application services only |
| `core/` | DI container, JWT auth, pydantic-settings config | Wires everything together |

No business logic in routers. Dependencies injected via `app/core/container.py` using FastAPI `Depends`.

**Architecture is enforced by tests.** `tests/unit/test_architecture.py` uses `ast.parse` to walk all `.py` files in `domain/` and `application/`, asserting they don't import from `infrastructure`, `api`, `fastapi`, `sqlalchemy`, or `redis`. New code in those layers must not break this.

### API — Current State

- **Live:** Health (`GET /api/v1/health`, `/health/ready`, `/version`), full DB schema via Alembic migration, `SqlAlchemy*Repository` implementations for story/article/entity/user/workspace, `RedisCacheGateway`.
- **Stubbed (empty `__init__.py`):** `infrastructure/connectors/`, `infrastructure/llm/`. These are Phase 7+ work.
- **Not yet implemented:** JWT auth (`core/security.py` referenced in README doesn't exist), all API routers except health (`auth`, `feed`, `stories`, `watchlists`, `exports`, `admin` are all stubs).
- **DB:** `apps/api/alembic/versions/0001_initial_schema.py` creates all 14 tables, `vector`/`pg_trgm` extensions, HNSW indexes on `articles.embedding` and `stories.cluster_centroid` (both `Vector(1024)`), GIN trigram indexes on headline/content.

### AI Pipeline (Celery)

All four task modules (`tasks/ingestion`, `tasks/nlp`, `tasks/llm`, `tasks/alerts`) are empty stubs. The pipeline is designed as:

1. Source connectors → ingestion queue → Normalizer → Dedup (MinHash/LSH)
2. Entity extraction (GLiNER) → Entity Resolution → Embedding (BGE → pgvector)
3. Story clustering: incremental nearest-centroid + nightly HDBSCAN full re-cluster
4. Sentiment (ModernBERT) → Executive Brief (Claude LLM) → Recommendations (confidence-gated)
5. Alert evaluation → WebSocket / email / Slack push

### Search Fast/Cold Path

- **Fast Path** — tracked keywords: served from Redis-cached precomputed payloads, zero computation at request time.
- **Cold Path** — untracked keyword: instant pgvector similarity + Postgres full-text (no LLM call), then auto-promotes to tracked so next search is Fast Path.

### Frontend — Current State

- **Live UI:** Full Flipboard-style feed at `/feed` with keyboard navigation (arrow keys), 4-page story view (Original / AI Insight / Cluster / Recommendations), fullscreen story at `/story/[id]`, admin sources page at `/admin/sources`. All powered by `lib/mock-data.ts` (8 mock stories) — no real API calls yet.
- **State:** Zustand store (`store/feedStore.ts`) for story/page navigation with `useKeyboardNav` hook. Auth store (`store/authStore.ts`) persists to `localStorage`.
- **Empty feature dirs:** `features/feed/api/`, `features/feed/hooks/`, `features/feed/store/`, `features/auth/store/` — TanStack Query wiring for real API calls goes here.
- **UI primitives:** shadcn/ui components in `components/ui/`. `Badge` has custom variants for `RiskLevel` (`low/medium/high/critical`) and `SentimentLabel` (`positive/negative/neutral/mixed`) mapped to CSS custom properties in `globals.css`.
- **Login:** `/login` links directly to `/feed`; JWT auth is Phase 6.

### Testing Patterns

**API tests** (`apps/api/tests/`):
- `conftest.py` defines `FakeCacheGateway` (in-memory dict), fixtures `fake_cache`, `fake_cache_down`, `app_with_fake_cache`, `client`. Sets required env vars before import.
- Integration tests in `tests/integration/` skip when Redis is unreachable.
- Unit tests in `tests/unit/` use only fakes — never mock framework internals.

**Frontend tests** (`apps/web/src/__tests__/`):
- RTL + Jest; `@/` alias configured in `jest.config.ts`.
- `store/feedStore.test.ts` tests all Zustand actions including boundary clamping.

**Workers** have no tests yet.

## Coding Standards

### Python

- `ruff` for lint + format; `mypy --strict` applied to `app/domain/` and `app/application/` layers. The `infrastructure/` and `api/` layers also run mypy but without `--strict`.
- Type hints on every function signature; no bare `except:`.
- `pydantic-settings` for all config; required env vars (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`) must fail fast on startup — never silently default secrets. `JWT_SECRET` validation rejects known-weak values (`changeme`, `secret`, etc.).
- Static protocol conformance checked at module bottom: `_: CacheGateway = RedisCacheGateway.__new__(RedisCacheGateway)` — use this pattern when implementing new gateway interfaces.

### TypeScript

- `strict: true` in all `tsconfig.json` files; no `any` without a `// TODO` justification comment.

### Environment

- `.env` is gitignored; only `.env.example` (repo root) is tracked.
- Copy `.env.example` → `.env` and fill in values before running locally.
- `JWT_SECRET` must be a long random string — the settings validator will reject weak values.
