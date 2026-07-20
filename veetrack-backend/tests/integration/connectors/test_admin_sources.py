"""Integration tests: GET/POST /api/v1/admin/sources (requires Postgres + Redis)."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.getenv("DATABASE_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _db_reachable() -> bool:
    async def _check() -> bool:
        try:
            import asyncpg

            conn = await asyncpg.connect(DATABASE_URL.replace("+asyncpg", ""))
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


requires_db = pytest.mark.skipif(
    not _db_reachable(),
    reason="Postgres not reachable — start Docker Compose",
)


def _make_client() -> TestClient:
    from app.core.container import _build_cache_gateway

    _build_cache_gateway.cache_clear()  # type: ignore[attr-defined]
    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _register_owner(client: TestClient) -> str:
    s = _uid()
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"admin_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"Admin Corp {s}",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


@requires_db
def test_create_source_returns_201() -> None:
    client = _make_client()
    token = _register_owner(client)
    resp = client.post(
        "/api/v1/admin/sources",
        json={"type": "newsdata", "is_active": True, "rate_limit_budget": 0.5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "newsdata"
    assert "id" in body


@requires_db
def test_list_sources_returns_created_source() -> None:
    client = _make_client()
    token = _register_owner(client)

    # Create a source first
    create_resp = client.post(
        "/api/v1/admin/sources",
        json={"type": "newsdata"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201

    list_resp = client.get(
        "/api/v1/admin/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200, list_resp.text
    sources = list_resp.json()
    assert isinstance(sources, list)
    ids = [s["id"] for s in sources]
    assert create_resp.json()["id"] in ids


@requires_db
def test_get_single_source() -> None:
    client = _make_client()
    token = _register_owner(client)

    create_resp = client.post(
        "/api/v1/admin/sources",
        json={"type": "newsdata", "rate_limit_budget": 1.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    source_id = create_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/admin/sources/{source_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == source_id
    assert body["calls_made_this_window"] == 0
    assert body["circuit_open"] is False


@requires_db
def test_sources_require_admin_role() -> None:
    client = _make_client()
    # No auth at all
    resp = client.get("/api/v1/admin/sources")
    assert resp.status_code == 401


@requires_db
def test_get_nonexistent_source_returns_404() -> None:
    client = _make_client()
    token = _register_owner(client)
    resp = client.get(
        "/api/v1/admin/sources/nonexistent-id",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
