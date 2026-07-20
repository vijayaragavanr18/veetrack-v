# VeeTrack Deployment Runbook

Covers Docker Compose (production) and Kubernetes deployments.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Setup](#2-environment-setup)
3. [First-Time Deployment (Docker Compose)](#3-first-time-deployment-docker-compose)
4. [Database Migrations](#4-database-migrations)
5. [Health Verification](#5-health-verification)
6. [Scaling Workers](#6-scaling-workers)
7. [Rolling Update Procedure](#7-rolling-update-procedure)
8. [Rollback Procedure](#8-rollback-procedure)
9. [Secrets Rotation](#9-secrets-rotation)
10. [Kubernetes Deployment](#10-kubernetes-deployment)
11. [Monitoring](#11-monitoring)
12. [Backup and Restore](#12-backup-and-restore)

---

## 1. Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| Docker Engine | 24.x | https://docs.docker.com/engine/install/ |
| Docker Compose v2 | 2.20+ | bundled with Docker Engine >= 24 |
| Git | 2.x | system package manager |
| `curl` | any | system package manager |
| `openssl` | any | system package manager |

Verify:

```bash
docker version
docker compose version    # must show v2.x, NOT v1 (docker-compose)
git --version
```

---

## 2. Environment Setup

### 2a. Copy and populate `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in **all** required variables:

| Variable | Required | Description |
|---|---|---|
| `POSTGRES_USER` | Yes | Postgres username (default: `veetrack`) |
| `POSTGRES_PASSWORD` | Yes | Postgres password — use a strong random value |
| `POSTGRES_DB` | Yes | Database name (default: `veetrack`) |
| `DATABASE_URL` | Yes | Full asyncpg URL: `postgresql+asyncpg://veetrack:<password>@postgres:5432/veetrack` |
| `REDIS_URL` | Yes | `redis://redis:6379/0` |
| `JWT_SECRET` | Yes | Long random string — minimum 32 chars, rejects `changeme` |
| `ANTHROPIC_API_KEY` | No* | Claude API key for AI brief generation (`sk-ant-...`) |
| `LLM_LOCAL_ENDPOINT` | No* | vLLM local endpoint URL (fallback if Anthropic not set) |
| `LLM_LOCAL_MODEL` | No* | Model ID for local LLM |
| `LLM_HOSTED_MODEL` | No | Claude model ID (default: `claude-haiku-4-5-20251001`) |
| `NEWSDATA_API_KEY` | No | Newsdata.io API key for news ingestion |
| `TWITTERAPI_IO_KEY` | No | TwitterAPI.io key for social ingestion |
| `SENTRY_DSN` | No | Sentry DSN for error tracking |
| `GRAFANA_ADMIN_PASSWORD` | Yes (prod) | Grafana admin password |
| `IMAGE_TAG` | No | Docker image tag to deploy (default: `latest`) |

*Either `ANTHROPIC_API_KEY` or `LLM_LOCAL_ENDPOINT` is required for the LLM pipeline.

Generate a strong `JWT_SECRET`:

```bash
openssl rand -base64 48
```

### 2b. TLS certificates

Place your certificates at:

```
infra/nginx/certs/cert.pem   # full certificate chain
infra/nginx/certs/key.pem    # private key (chmod 600)
```

For Let's Encrypt with certbot:

```bash
certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem infra/nginx/certs/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   infra/nginx/certs/key.pem
```

---

## 3. First-Time Deployment (Docker Compose)

```bash
# Build all images (from monorepo root)
docker compose -f infra/docker-compose.prod.yml --env-file .env build

# Start all services in detached mode
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d

# Confirm all containers are running (no "Restarting" or "Exit" status)
docker compose -f infra/docker-compose.prod.yml ps
```

Expected healthy services: `postgres`, `redis`, `api`, `worker`, `beat`, `web`, `nginx`, `prometheus`, `grafana`.

**Run database migrations before the API receives traffic** — see Section 4.

---

## 4. Database Migrations

Migrations are managed by Alembic. Always run them with the API container's Python environment to ensure the same dependency versions.

### Apply all pending migrations

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic upgrade head
```

### Check current migration state

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic current
```

### View migration history

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic history --verbose
```

### Downgrade one step (emergency only)

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic downgrade -1
```

---

## 5. Health Verification

### API health endpoints

```bash
# Basic liveness (no DB, no Redis)
curl -s http://localhost/api/v1/health | jq .

# Readiness (checks DB + Redis connectivity)
curl -s http://localhost/api/v1/health/ready | jq .

# Version
curl -s http://localhost/api/v1/version | jq .
```

Expected response for `/health`:

```json
{"status": "ok"}
```

### Check service logs

```bash
# Tail last 100 lines from api
docker compose -f infra/docker-compose.prod.yml logs --tail=100 -f api

# All services at once
docker compose -f infra/docker-compose.prod.yml logs --tail=50 -f
```

### Verify Celery worker is receiving tasks

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec worker celery -A celery_app inspect active
```

---

## 6. Scaling Workers

Scale the worker pool horizontally (without affecting beat or other services):

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    up -d --scale worker=4
```

Scale back down:

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    up -d --scale worker=2
```

**Note:** `beat` must always run as exactly **1 replica**. Never scale beat — duplicate instances cause tasks to fire multiple times.

---

## 7. Rolling Update Procedure

### Build and tag new images

```bash
export IMAGE_TAG=v1.2.3   # or a git SHA: $(git rev-parse --short HEAD)

docker compose -f infra/docker-compose.prod.yml --env-file .env \
    build --no-cache

docker tag veetrack-api:latest   veetrack-api:$IMAGE_TAG
docker tag veetrack-worker:latest veetrack-worker:$IMAGE_TAG
docker tag veetrack-beat:latest   veetrack-beat:$IMAGE_TAG
docker tag veetrack-web:latest    veetrack-web:$IMAGE_TAG
```

### Run migrations first (if schema changed)

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic upgrade head
```

### Deploy new containers (zero-downtime)

```bash
# Recreate api and web — nginx keeps routing to healthy containers
IMAGE_TAG=$IMAGE_TAG docker compose \
    -f infra/docker-compose.prod.yml --env-file .env \
    up -d --no-deps api web worker beat
```

### Verify after deploy

```bash
curl -s http://localhost/api/v1/health/ready | jq .
curl -s http://localhost/api/v1/version | jq .
```

---

## 8. Rollback Procedure

### Identify previous image tag

```bash
docker images veetrack-api --format "table {{.Tag}}\t{{.CreatedAt}}"
```

### Retag and redeploy

```bash
export ROLLBACK_TAG=v1.2.2

docker tag veetrack-api:$ROLLBACK_TAG   veetrack-api:latest
docker tag veetrack-worker:$ROLLBACK_TAG veetrack-worker:latest
docker tag veetrack-beat:$ROLLBACK_TAG   veetrack-beat:latest
docker tag veetrack-web:$ROLLBACK_TAG    veetrack-web:latest

docker compose -f infra/docker-compose.prod.yml --env-file .env \
    up -d --no-deps api web worker beat
```

### If migration rollback is needed

```bash
# Downgrade to the revision matching the rollback tag
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec api uv run alembic downgrade <target_revision>
```

Find revision IDs with `alembic history`.

---

## 9. Secrets Rotation

### Rotating `JWT_SECRET`

**Impact:** All currently-issued JWTs are invalidated immediately. Every logged-in user will be signed out and must re-authenticate.

1. Generate a new secret:

   ```bash
   openssl rand -base64 48
   ```

2. Update `.env`:

   ```
   JWT_SECRET=<new-secret>
   ```

3. Redeploy the API (and beat/worker if they also validate JWTs):

   ```bash
   docker compose -f infra/docker-compose.prod.yml --env-file .env \
       up -d --no-deps api
   ```

4. Notify users that an active session re-login is required.

### Rotating `POSTGRES_PASSWORD`

1. Update the password in Postgres first:

   ```bash
   docker compose -f infra/docker-compose.prod.yml --env-file .env \
       exec postgres psql -U veetrack -c "ALTER USER veetrack PASSWORD 'new-password';"
   ```

2. Update `.env` with the new password (both `POSTGRES_PASSWORD` and `DATABASE_URL`).

3. Restart the API and workers:

   ```bash
   docker compose -f infra/docker-compose.prod.yml --env-file .env \
       up -d --no-deps api worker beat
   ```

### Rotating `ANTHROPIC_API_KEY`

1. Generate a new key from the Anthropic console.
2. Update `.env`.
3. Restart `api` and `worker`:

   ```bash
   docker compose -f infra/docker-compose.prod.yml --env-file .env \
       up -d --no-deps api worker
   ```

---

## 10. Kubernetes Deployment

### Prerequisites

- `kubectl` configured against your target cluster
- NVIDIA device plugin installed (for GPU nodes running `worker-nlp`)
- cert-manager installed for TLS (`kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml`)
- ingress-nginx controller installed

### Apply manifests

```bash
# Create namespace first
kubectl apply -f infra/k8s/namespace.yaml

# Populate secrets — edit infra/k8s/secrets.yaml, replace all CHANGE_ME values
# with real base64-encoded secrets BEFORE applying.
kubectl apply -f infra/k8s/secrets.yaml
kubectl apply -f infra/k8s/configmap.yaml

# Data tier
kubectl apply -f infra/k8s/postgres.yaml
kubectl apply -f infra/k8s/redis.yaml

# Wait for data tier to be ready
kubectl -n veetrack rollout status statefulset/postgres
kubectl -n veetrack rollout status deployment/redis

# Application tier
kubectl apply -f infra/k8s/api.yaml
kubectl apply -f infra/k8s/worker.yaml
kubectl apply -f infra/k8s/web.yaml

# Ingress — update host in infra/k8s/ingress.yaml before applying
kubectl apply -f infra/k8s/ingress.yaml
```

### Run migrations

```bash
kubectl -n veetrack exec deploy/api -- uv run alembic upgrade head
```

### GPU node requirements for `worker-nlp`

The `worker-nlp` Deployment uses `nodeSelector: gpu: "true"` and tolerates the `gpu=true:NoSchedule` taint.

Label and taint your GPU node(s):

```bash
kubectl label node <gpu-node-name> gpu=true
kubectl taint node <gpu-node-name> gpu=true:NoSchedule
```

Install the NVIDIA device plugin:

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.16.0/deployments/static/nvidia-device-plugin.yml
```

### Kubernetes rolling updates

```bash
# Update image tag
kubectl -n veetrack set image deployment/api api=veetrack-api:v1.2.3
kubectl -n veetrack set image deployment/web web=veetrack-web:v1.2.3
kubectl -n veetrack set image deployment/worker-io worker=veetrack-worker:v1.2.3
kubectl -n veetrack set image deployment/worker-nlp worker=veetrack-worker:v1.2.3
kubectl -n veetrack set image deployment/beat beat=veetrack-beat:v1.2.3

# Monitor rollout
kubectl -n veetrack rollout status deployment/api
```

### Kubernetes rollback

```bash
kubectl -n veetrack rollout undo deployment/api
kubectl -n veetrack rollout undo deployment/web
```

---

## 11. Monitoring

### Prometheus

Prometheus scrapes the API's `/metrics` endpoint (via `prometheus-fastapi-instrumentator`).

| URL | Access |
|---|---|
| `http://localhost:9099` | Direct Prometheus UI (Docker Compose, localhost-bound) |
| `http://prometheus:9090` | In-cluster (Kubernetes) |

Configuration: `infra/prometheus.yml`

### Grafana

| URL | Access |
|---|---|
| `http://localhost:3001` | Docker Compose (localhost-bound) |
| Default credentials | admin / `$GRAFANA_ADMIN_PASSWORD` |

Dashboards are pre-provisioned from `infra/grafana/dashboards/`.

### Key metrics to alert on

| Metric | Alert threshold |
|---|---|
| `http_request_duration_seconds_p99` | > 2s |
| `celery_task_failure_rate` | > 5% |
| `postgres_connections_used` | > 80% of `max_connections` |
| `redis_memory_used_ratio` | > 85% |
| API pod restarts | > 2 in 10 minutes |

---

## 12. Backup and Restore

### Postgres backup (Docker Compose)

```bash
# Dump to a timestamped file
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec postgres pg_dump -U veetrack -Fc veetrack \
    > backups/veetrack_$(date +%Y%m%d_%H%M%S).dump
```

Automate with cron:

```cron
0 2 * * * cd /path/to/veetrack && docker compose -f infra/docker-compose.prod.yml --env-file .env exec -T postgres pg_dump -U veetrack -Fc veetrack > backups/veetrack_$(date +\%Y\%m\%d).dump 2>&1
```

### Postgres restore

```bash
# Stop the API and workers to prevent writes during restore
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    stop api worker beat

# Drop and recreate the database
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec postgres dropdb -U veetrack veetrack
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec postgres createdb -U veetrack veetrack

# Restore from dump
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    exec -T postgres pg_restore -U veetrack -d veetrack \
    < backups/veetrack_20260101_020000.dump

# Restart services
docker compose -f infra/docker-compose.prod.yml --env-file .env \
    start api worker beat
```

### Redis backup

Redis AOF files are persisted in the `redis_data` named volume. To export:

```bash
docker run --rm \
    -v veetrack-prod_redis_data:/data \
    -v $(pwd)/backups:/backup \
    alpine tar czf /backup/redis_$(date +%Y%m%d).tar.gz /data
```

### Kubernetes backup

For Kubernetes, use [Velero](https://velero.io/) for cluster-level backup including PVCs:

```bash
velero backup create veetrack-backup --include-namespaces veetrack
velero restore create --from-backup veetrack-backup
```
