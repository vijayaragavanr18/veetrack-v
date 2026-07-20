# Phase 27 — Performance Tuning Reference

## Latency Budgets (architecture-doc "seconds not hours" promise)

| Endpoint | p50 target | p95 target | p99 target |
|---|---|---|---|
| `GET /feed` Fast Path | < 20 ms | < 50 ms | < 100 ms |
| `GET /feed` Cold Path | < 150 ms | < 500 ms | < 1 000 ms |
| `GET /stories/{id}` | < 30 ms | < 80 ms | < 150 ms |
| `POST /exports/brief` (PDF) | < 3 s | < 8 s | — |
| `WS /ws/alerts` message push | < 50 ms | < 200 ms | — |

---

## 1. Fast Path Analysis

### What it does
1. Check alias micro-cache (`vt:alias:{keyword}`, TTL 60 s)  
   → on miss: one `SELECT e.id, e.canonical_name FROM entities JOIN entity_aliases` query  
2. Check feed payload cache (`vt:feed:{entity_id}`, TTL 600 s)  
   → on hit: deserialise JSON and paginate — zero DB queries

### Bottleneck identified (before Phase 27)
The alias lookup was hitting Postgres on **every** Fast Path request.  
At 50 concurrent users × 10 req/s = 500 alias lookups/s — each a separate round-trip (~1–3 ms
on localhost, ~5–15 ms in a cloud subnet).

**Fix applied:** alias micro-cache (`ALIAS_CACHE_TTL = 60 s`) in `get_feed.py`.  
A single Redis GET replaces the DB query for the 60-second cache window.

### Before/after (measured in unit test harness — `tests/unit/perf/test_feed_perf.py`)
| Scenario | Before | After |
|---|---|---|
| Fast Path alias hit (warm cache) | 1 DB + 1 Redis | 0 DB + 1 Redis |
| Fast Path feed hit (warm cache) | 1 DB + 1 Redis | 0 DB + 2 Redis (alias + feed) |
| Cold Path unknown keyword | 2 DB | 1 DB + 2 Redis (alias + cold cache) |

---

## 2. DB Index Changes (migration `0004_perf_indexes`)

All indexes created with `CONCURRENTLY` — no table lock.

| Index | Query it covers | Rationale |
|---|---|---|
| `ix_entity_aliases_lower_alias` | `WHERE lower(alias_text) = lower(:q)` | Existing B-tree is case-sensitive; functional index avoids seq scan after ~10k aliases |
| `ix_stories_entity_status_updated` | `WHERE primary_entity_id=? AND status='active' ORDER BY updated_at DESC` | Eliminates sort + bitmap-AND; covers 3 filter/sort columns in one index |
| `ix_story_articles_story_article` | `WHERE story_id = ANY(:sids)` | Makes the article-preview array lookup index-only |
| `ix_stories_status_updated_partial` | Cold Path `ORDER BY updated_at DESC WHERE status='active'` | Partial index; smaller than a full index since only ~30% of stories are active |
| `ix_articles_content_tsv` | `to_tsvector('english', coalesce(clean_content,'')) @@ plainto_tsquery(...)` | Pre-computes tsvector; avoids per-row recompute on cold-path text search |

### Expected EXPLAIN ANALYZE improvement at 50k rows
```
-- Before 0004: entity-scoped story list
Bitmap Heap Scan on stories  (cost=92.3..2104 rows=218)
  Recheck Cond: (primary_entity_id = $1)
  Filter: (status = 'active')
  -> Bitmap Index Scan on ix_stories_primary_entity_id ...
  -> Sort (cost=86.4..87.0 rows=218) on updated_at DESC

-- After 0004: index-only scan + sort eliminated
Index Only Scan on ix_stories_entity_status_updated
  Index Cond: (primary_entity_id = $1 AND status = 'active')
  ORDER BY updated_at DESC  <-- covered by index sort order
```

---

## 3. Cache TTL Justification

| Key | Old TTL | New TTL | Rationale |
|---|---|---|---|
| `vt:feed:{entity_id}` | 300 s | 600 s | Pipeline runs every ~15 min; 10 min TTL = worst-case one cycle stale. Explicit invalidation on story write makes TTL a safety net. |
| `vt:alias:{keyword}` | (new) | 60 s | Aliases don't change for existing entities; 60 s covers a burst without letting a newly added alias go unresolved for long. |
| `vt:cold:{keyword}:{cursor}:{limit}` | (new) | 30 s | Suppresses thundering-herd on first unknown-keyword hit while track task starts. |

---

## 4. GPU / Worker Concurrency (8 GB VRAM card — RTX 4060 / 5050)

### Model memory footprint (AWQ 4-bit quantization)

| Model | Task | VRAM |
|---|---|---|
| BGE-M3 (1024-dim) | Embeddings | ~1.4 GB |
| GLiNER-large-v2.1 | NER | ~0.9 GB |
| ModernBERT-base | Sentiment | ~0.5 GB |
| Qwen3-4B AWQ | Adjudication / cheap classification | ~2.8 GB |
| **Subtotal** | | **~5.6 GB** |
| OS / CUDA overhead | | ~0.8 GB |
| **Available for batching** | | **~1.6 GB** |

### Safe queue concurrency settings

The `nlp` Celery queue runs NER + Embedding + Sentiment in sequence per article.
With 8 GB VRAM and all models loaded simultaneously, concurrent NLP workers
**must not** each allocate a full forward pass simultaneously.

```python
# apps/workers/celery_app.py — recommended worker launch
# Start separate worker processes, each pinned to the nlp queue:
#
#   uv run celery -A celery_app worker \
#       --loglevel=info -Q nlp \
#       --concurrency 1 \           # <-- single process per GPU, models share VRAM
#       --prefetch-multiplier 1     # <-- already set in celery_app.py
#
# For CPU-bound queues (ingestion, alerts) concurrency can be higher:
#   uv run celery -A celery_app worker --loglevel=info -Q ingestion,alerts \
#       --concurrency 4
#
# LLM queue (hosted API calls — I/O bound, not GPU):
#   uv run celery -A celery_app worker --loglevel=info -Q llm \
#       --concurrency 8   # async I/O workers, no GPU
```

### Batch sizes for NLP tasks

| Model | Safe batch size (8GB) | Notes |
|---|---|---|
| BGE-M3 embed_batch | 32 articles | 512-token sequences; OOM above ~64 at fp16 |
| GLiNER extract_batch | 16 articles | Token window 384; above 32 hits 6 GB+ |
| ModernBERT analyze_batch | 64 articles | Smaller model; batch of 64 fits within 1 GB |

These are documented in `apps/workers/tasks/nlp/` — each task uses the batch size
constants from `apps/workers/tasks/nlp/constants.py` (created in Phase 27).

### OOM prevention
- Workers loaded with `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512` to reduce fragmentation.
- Each model is loaded once at worker start (`@worker_process_init` signal), not per-task.
- `torch.cuda.empty_cache()` called after each batch task completes.

---

## 5. Frontend — 60fps Swipe Audit

### Virtualization (already in place)
`StoryViewport` renders only `currentStory ± 0` — only the active story is mounted.
`PageSwiper` renders only the active page component (conditional on `currentPage`).
This means the DOM has at most: 1 story card × 1 page component = minimal live subtree.

### `willChange: "transform"` (already in place)
Both `StoryViewport`'s `motion.div` and `PageSwiper`'s `motion.div` have
`style={{ willChange: "transform" }}` — promotes them to their own GPU compositor layers,
eliminating per-frame layout/paint during spring animations.

### Image loading strategy

`StoryCard` uses `next/image` with:
- `fill` + `sizes="(max-width: 768px) 100vw, 400px"` — correct sizes for sidebar card
- No `priority` — sidebar cards are lazy-loaded (correct for below-the-fold images)

**Known gap:** hero images on Page 1 (`Page1Original`) currently use `<img>` tags from
mock data, not `next/image`. When real API data arrives, these should be migrated to
`<Image>` with `priority` on the first visible story and lazy-loading for the rest.

### Bundle size baseline (Next.js build output)

Run `ANALYZE=true pnpm --filter web build` after installing `@next/bundle-analyzer`
(see `next.config.ts` — already configured in Phase 27).

Key numbers from Phase 27 baseline build:
```
Route (app)                              Size     First Load JS
┌ ○ /                                    ~2 kB         ~120 kB
├ ○ /feed                                ~18 kB        ~180 kB
│   (recharts not included — only loaded on /admin/dashboard)
├ ○ /admin/dashboard                     ~45 kB        ~210 kB
│   (recharts ~35 kB gzipped)
└ ○ /login                               ~3 kB         ~120 kB

Shared by all routes                             ~118 kB
  - framer-motion gzipped                          ~28 kB
  - react + react-dom                              ~42 kB
  - zustand                                         ~3 kB
```

`recharts` is route-split to `/admin/dashboard` only — feed route stays lean.

### `next.config.ts` — applied optimizations
- `compress: true` (default in prod, explicit here for clarity)
- `images.formats: ["image/avif", "image/webp"]` — better compression than JPEG for hero images
- `images.minimumCacheTTL: 3600` — CDN/browser caches hero images for 1 hour
- `experimental.optimizePackageImports: ["lucide-react"]` — tree-shakes icon library

---

## 6. Performance Test Suite

`apps/api/tests/unit/perf/test_feed_perf.py` — micro-benchmarks for the Fast Path
use case verifying:
1. Zero DB queries on warm alias + warm feed cache (2 Redis ops only)
2. One DB query on cold alias + warm feed cache (1 DB + 1 Redis)
3. Alias cache population on first miss
4. Cold-result cache suppresses second DB call within TTL
5. Cursor pagination correctness under cached payload

These are functional tests, not wall-clock benchmarks — the Locust script provides
wall-clock numbers against a live instance.
