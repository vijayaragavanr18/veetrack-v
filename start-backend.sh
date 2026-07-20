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

# ── 3. vLLM server (Qwen for AI summaries + recommendations) ─────────────────
# Requires: pip install vllm  OR  uv add vllm
# First run downloads the model (~2GB). Skip with: SKIP_VLLM=1 ./start-backend.sh
if [ "${SKIP_VLLM}" != "1" ] && command -v python3 &>/dev/null; then
  if python3 -c "import vllm" 2>/dev/null; then
    echo "▶  Starting vLLM (Qwen2.5-3B) on http://localhost:8080 ..."
    python3 -m vllm.entrypoints.openai.api_server \
      --model Qwen/Qwen2.5-3B-Instruct \
      --port 8080 \
      --max-model-len 4096 \
      --dtype auto \
      --gpu-memory-utilization 0.88 &
    PIDS+=($!)
    sleep 5
  else
    echo "⚠   vLLM not installed — AI summaries/recommendations will be skipped."
    echo "    To install: pip install vllm  (needs CUDA GPU for best performance)"
    echo "    Then re-run this script. Or: SKIP_VLLM=1 ./start-backend.sh"
  fi
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
