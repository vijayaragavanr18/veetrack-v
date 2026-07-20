"""Integration tests for health endpoints against real Dockerized Redis.

Run only when Docker Compose infrastructure is up:
  docker compose -f infra/docker-compose.yml --env-file .env up -d

Skip automatically if REDIS_URL points to an unreachable host.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.cache.redis_client import RedisCacheGateway


def _redis_reachable() -> bool:
    """Return True if the configured Redis is reachable."""
    import asyncio

    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    gw = RedisCacheGateway.from_url(url)
    try:
        return asyncio.run(gw.ping())
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis not reachable — start Docker Compose before running integration tests",
)


@requires_redis
def test_liveness_against_real_infra() -> None:
    """GET /api/v1/health returns 200 with real infra running."""
    from app.main import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@requires_redis
def test_readiness_ok_against_real_redis() -> None:
    """GET /api/v1/health/ready returns 200 when real Redis is up."""
    from app.main import create_app

    client = TestClient(create_app())
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["redis"] == "ok"
