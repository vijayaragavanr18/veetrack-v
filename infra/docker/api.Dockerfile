# syntax=docker/dockerfile:1.7
# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv — pinned to a specific release for reproducibility
RUN pip install --no-cache-dir uv==0.6.14

# Copy only the dependency manifest + lockfile first so Docker can cache this
# layer independently of source-code changes.
COPY apps/api/pyproject.toml apps/api/uv.lock ./

# Sync production deps into an isolated venv under /app/.venv
# --frozen  : enforce lockfile, fail if out of date
# --no-dev  : skip dev/test extras
RUN uv sync --frozen --no-dev

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Harden: no .pyc files, unbuffered stdout/stderr so logs stream to Docker
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root user (uid 1000) — never run as root in production
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# curl is needed for the HEALTHCHECK; install before dropping to non-root
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the fully-resolved virtualenv from builder — no pip/uv in final image
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv

# Copy application source (no tests, no .env, no dev assets)
COPY --chown=appuser:appuser apps/api/app ./app
COPY --chown=appuser:appuser apps/api/alembic ./alembic
COPY --chown=appuser:appuser apps/api/alembic.ini ./alembic.ini

USER appuser

EXPOSE 8000

# Liveness probe — hits the lightweight /health endpoint (no DB query)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 4 Uvicorn workers; override WEB_CONCURRENCY at runtime for different sizes
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
