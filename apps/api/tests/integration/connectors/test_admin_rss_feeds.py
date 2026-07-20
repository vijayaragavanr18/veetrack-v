"""Integration tests: RSS feed URL CRUD — GET/POST/DELETE /api/v1/admin/sources/{id}/rss-feeds.

Requires Postgres (Docker Compose).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.getenv("DATABASE_URL", "")


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
            "email": f"rssadmin_{s}@example.com",
            "password": "Pass1234!",
            "workspace_name": f"RSS Corp {s}",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _create_rss_source(client: TestClient, token: str) -> str:
    """Create an RSS source row and return its ID."""
    resp = client.post(
        "/api/v1/admin/sources",
        json={"type": "rss", "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@requires_db
def test_list_feeds_empty_initially() -> None:
    client = _make_client()
    token = _register_owner(client)
    source_id = _create_rss_source(client, token)

    resp = client.get(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_id"] == source_id
    assert body["feed_urls"] == []


@requires_db
def test_add_feed_url() -> None:
    client = _make_client()
    token = _register_owner(client)
    source_id = _create_rss_source(client, token)

    resp = client.post(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        json={"url": "https://feeds.example.com/rss"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "https://feeds.example.com/rss" in body["feed_urls"]


@requires_db
def test_add_duplicate_feed_returns_409() -> None:
    client = _make_client()
    token = _register_owner(client)
    source_id = _create_rss_source(client, token)

    url = "https://feeds.example.com/rss"
    client.post(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        json={"url": url},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        json={"url": url},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text


@requires_db
def test_remove_feed_url() -> None:
    client = _make_client()
    token = _register_owner(client)
    source_id = _create_rss_source(client, token)

    feed_url = "https://feeds.example.com/rss"
    client.post(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        json={"url": feed_url},
        headers={"Authorization": f"Bearer {token}"},
    )

    del_resp = client.delete(
        f"/api/v1/admin/sources/{source_id}/rss-feeds/0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204, del_resp.text

    list_resp = client.get(
        f"/api/v1/admin/sources/{source_id}/rss-feeds",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.json()["feed_urls"] == []


@requires_db
def test_remove_feed_out_of_range_returns_404() -> None:
    client = _make_client()
    token = _register_owner(client)
    source_id = _create_rss_source(client, token)

    resp = client.delete(
        f"/api/v1/admin/sources/{source_id}/rss-feeds/99",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


@requires_db
def test_rss_feeds_require_auth() -> None:
    client = _make_client()
    resp = client.get("/api/v1/admin/sources/any-id/rss-feeds")
    assert resp.status_code == 401
