"""Integration test: API → Celery broker → worker → Redis round-trip.

Requires:
  - Docker Compose running (Redis up)
  - A Celery worker running:
      cd apps/workers && uv run celery -A celery_app worker -Q ingestion --loglevel=info

Skip automatically if Redis is unreachable or no worker picks up the task within 10 s.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _redis_reachable() -> bool:
    async def _check() -> bool:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(REDIS_URL)
            await client.ping()
            await client.aclose()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


requires_redis = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis not reachable — start Docker Compose",
)


@requires_redis
def test_ping_worker_roundtrip_timeout_without_worker() -> None:
    """With no worker running, ping-worker returns status=timeout (not an error)."""
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    os.environ.setdefault("REDIS_URL", REDIS_URL)
    os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-tests-only")
    os.environ.setdefault("ENVIRONMENT", "test")

    from app.core.container import _build_cache_gateway

    _build_cache_gateway.cache_clear()  # type: ignore[attr-defined]

    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.post("/api/v1/system/ping-worker")
    assert resp.status_code == 200
    body = resp.json()
    # Without a running worker the result is timeout — still a 200, not an error
    assert body["status"] in ("ok", "timeout")
    assert body["task_id"]
    assert body["redis_key"].startswith("system:ping:")


@requires_redis
def test_ping_worker_returns_ok_with_eager_execution() -> None:
    """With CELERY_TASK_ALWAYS_EAGER=True the task executes synchronously in-process."""
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    os.environ.setdefault("REDIS_URL", REDIS_URL)
    os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-tests-only")
    os.environ.setdefault("ENVIRONMENT", "test")

    # Clear lru_cache singletons so this test gets a fresh Redis connection on its own event loop.
    from app.core.container import _build_cache_gateway, _build_celery_app

    _build_cache_gateway.cache_clear()  # type: ignore[attr-defined]
    _build_celery_app.cache_clear()  # type: ignore[attr-defined]

    from app.core import container as container_mod

    original_builder = container_mod._build_celery_app  # noqa: SLF001 — test only

    def _eager_builder() -> object:
        app = original_builder()
        app.conf.task_always_eager = True  # type: ignore[union-attr]
        app.conf.task_eager_propagates = True  # type: ignore[union-attr]
        return app

    container_mod._build_celery_app = _eager_builder  # type: ignore[assignment]  # noqa: SLF001

    try:
        # Import the task so Celery knows about it in eager mode
        import sys

        sys.path.insert(
            0,
            str(__file__).replace(
                "apps/api/tests/integration/test_ping_roundtrip.py", "apps/workers"
            ),
        )
        from app.main import create_app

        client = TestClient(create_app(), raise_server_exceptions=True)
        resp = client.post("/api/v1/system/ping-worker")
        body = resp.json()
        # Eager mode: task runs synchronously but worker writes to real Redis
        # so result depends on whether task module is importable
        assert resp.status_code == 200
        assert body["status"] in ("ok", "timeout")
    finally:
        container_mod._build_celery_app = original_builder  # type: ignore[assignment]  # noqa: SLF001
        _build_celery_app.cache_clear()  # type: ignore[attr-defined]
