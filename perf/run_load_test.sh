#!/usr/bin/env bash
# Phase 27 load-test runner.
# Usage: ./perf/run_load_test.sh [host] [users] [spawn-rate] [duration]
#
# Requirements:
#   1. API server running: cd apps/api && uv run uvicorn app.main:app --workers 4
#   2. Redis + Postgres running: docker compose -f infra/docker-compose.yml --env-file .env up -d
#   3. A valid JWT: export LOCUST_JWT_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
#        -H "Content-Type: application/json" \
#        -d '{"email":"admin@test.com","password":"changeme"}' | jq -r .access_token)
#   4. Some tracked entities seeded in DB (run the ingestion pipeline or seed script)

set -euo pipefail

HOST="${1:-http://localhost:8000}"
USERS="${2:-50}"
SPAWN_RATE="${3:-10}"
DURATION="${4:-60s}"
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
RESULTS_DIR="perf/results"

mkdir -p "$RESULTS_DIR"

echo "=== VeeTrack Load Test ==="
echo "  Host:        $HOST"
echo "  Users:       $USERS"
echo "  Spawn rate:  $SPAWN_RATE/s"
echo "  Duration:    $DURATION"
echo "  Results dir: $RESULTS_DIR"
echo ""

cd apps/api
uv run locust \
    -f ../../perf/locustfile.py \
    --host "$HOST" \
    --users "$USERS" \
    --spawn-rate "$SPAWN_RATE" \
    --run-time "$DURATION" \
    --headless \
    --csv "../../$RESULTS_DIR/run_$TIMESTAMP" \
    --html "../../$RESULTS_DIR/run_$TIMESTAMP.html"

echo ""
echo "Results saved to $RESULTS_DIR/run_$TIMESTAMP.*"
echo ""
echo "=== Summary ==="
if [ -f "../../$RESULTS_DIR/run_${TIMESTAMP}_stats.csv" ]; then
    # Print Name, Requests, Failures, p50, p95, p99
    python3 - <<'PY'
import csv, sys, os
results_dir = sys.argv[1] if len(sys.argv) > 1 else "perf/results"
# find latest stats csv
import glob
files = sorted(glob.glob(f"{results_dir}/*_stats.csv"))
if not files:
    print("No stats CSV found")
    sys.exit(0)
fname = files[-1]
rows = list(csv.DictReader(open(fname)))
print(f"{'Endpoint':<45} {'Reqs':>6} {'Fail':>5} {'p50ms':>7} {'p95ms':>7} {'p99ms':>7}")
print("-" * 85)
for r in rows:
    if r.get('Name') == 'Aggregated':
        continue
    print(f"{r.get('Name',''):<45} {r.get('Request Count',''):>6} {r.get('Failure Count',''):>5} "
          f"{r.get('50%',''):>7} {r.get('95%',''):>7} {r.get('99%',''):>7}")
print("-" * 85)
agg = next((r for r in rows if r.get('Name') == 'Aggregated'), None)
if agg:
    print(f"{'TOTAL':<45} {agg.get('Request Count',''):>6} {agg.get('Failure Count',''):>5} "
          f"{agg.get('50%',''):>7} {agg.get('95%',''):>7} {agg.get('99%',''):>7}")
PY
fi
