# syntax=docker/dockerfile:1.7
# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv==0.6.14

# Copy manifests first for cache efficiency
COPY apps/workers/pyproject.toml apps/workers/uv.lock ./

RUN uv sync --frozen --no-dev

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    # PyTorch memory allocator — avoids OOM fragmentation on GPU nodes
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    # Celery best-practice: use fork (not spawn) on Linux
    CELERY_WORKER_POOL=prefork

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv

# Copy worker source
COPY --chown=appuser:appuser apps/workers/ .

USER appuser

# Healthcheck: asks the running worker process to respond to a ping
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD celery -A celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

# Run all four application queues; override CMD per-service in compose/k8s
CMD ["celery", "-A", "celery_app", "worker", \
     "--loglevel=info", \
     "-Q", "ingestion,nlp,llm,alerts", \
     "--concurrency=4"]
