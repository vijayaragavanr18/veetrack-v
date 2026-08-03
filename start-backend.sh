#!/usr/bin/env bash
# =============================================================================
# VeeTrack Backend — starts everything in one terminal
#
#   Terminal 1 (backend):   ./start-backend.sh
#   Terminal 2 (frontend):  ./start-frontend.sh
#
# Starts: Docker (Postgres + Redis) → FastAPI → Celery Worker → Celery Beat
# Stop everything: Ctrl+C  (kills all child processes automatically)
# =============================================================================
set -e
cd "$(dirname "$0")"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example → .env and fill in values."
  exit 1
fi
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# ── Trap: kill all child processes on Ctrl+C ──────────────────────────────────
PIDS=()
cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  docker compose -f infra/docker-compose.yml --env-file .env down 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── 1. Docker (Postgres + Redis) ──────────────────────────────────────────────
echo "▶  Starting Postgres + Redis..."
docker compose -f infra/docker-compose.yml --env-file .env up -d
sleep 3

# ── 2. Run Alembic migrations ─────────────────────────────────────────────────
echo "▶  Running DB migrations..."
cd veetrack-backend
PYTHONPATH=src uv run alembic upgrade head 2>/dev/null || true

# ── 3. Ollama (Qwen2.5:3b for AI summaries + recommendations) ────────────────
# Requires: curl -fsSL https://ollama.com/install.sh | sh
# First run pulls the model (~2GB). Skip with: SKIP_OLLAMA=1 ./start-backend.sh
if [ "${SKIP_OLLAMA}" != "1" ] && command -v ollama &>/dev/null; then
  if ! curl -sf http://localhost:11434/ >/dev/null 2>&1; then
    echo "▶  Starting Ollama daemon on http://localhost:11434 ..."
    ollama serve &>/dev/null &
    sleep 2
  else
    echo "▶  Ollama daemon already running."
  fi
  if ! ollama list | grep -q "qwen2.5:7b"; then
    echo "▶  Pulling qwen2.5:7b (~2 GB, one-time)..."
    ollama pull qwen2.5:7b
  fi
else
  echo "⚠   Ollama not installed — AI summaries/recommendations will be skipped."
  echo "    To install: curl -fsSL https://ollama.com/install.sh | sh"
  echo "    Then re-run this script. Or: SKIP_OLLAMA=1 ./start-backend.sh"
fi

# ── 4. FastAPI backend ────────────────────────────────────────────────────────
echo "▶  Starting FastAPI on http://localhost:8000 ..."
PYTHONPATH=src uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
PIDS+=($!)
sleep 4

# ── 5. Celery Worker (all queues) ─────────────────────────────────────────────
echo "▶  Starting Celery worker (ingestion + nlp + llm + alerts)..."
PYTHONPATH=src \
APIDIRECT_API_KEY="$APIDIRECT_API_KEY" \
uv run celery -A workers.celery_app worker \
  --loglevel=info \
  -Q ingestion,nlp,llm,alerts \
  --concurrency=2 &
PIDS+=($!)
sleep 3

# ── 6. Celery Beat scheduler ──────────────────────────────────────────────────
echo "▶  Starting Celery Beat (auto-ingestion every 15 min)..."
PYTHONPATH=src \
APIDIRECT_API_KEY="$APIDIRECT_API_KEY" \
uv run celery -A workers.celery_app beat \
  --loglevel=info \
  -s /tmp/celerybeat-schedule &
PIDS+=($!)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓  Backend running"
echo "  API  →  http://localhost:8000"
echo "  Docs →  http://localhost:8000/docs"
echo "  Press Ctrl+C to stop everything"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for all children
wait
