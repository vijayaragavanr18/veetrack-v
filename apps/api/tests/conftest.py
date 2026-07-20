"""Shared pytest fixtures.

Tests that need a running API use `client`. Tests that exercise domain/application
logic use `fake_cache` and `fake_settings` — no Docker required.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure test-safe env vars before any app import
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-tests-only")
os.environ.setdefault("ENVIRONMENT", "test")


from app.core.config import Settings, get_settings  # noqa: E402
from app.core.container import get_cache_gateway  # noqa: E402
from app.main import create_app  # noqa: E402


class FakeCacheGateway:
    """In-memory CacheGateway — no Redis required."""

    def __init__(self, *, available: bool = True) -> None:
        self._store: dict[str, bytes] = {}
        self._available = available

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ping(self) -> bool:
        return self._available


@pytest.fixture()
def fake_cache() -> FakeCacheGateway:
    """Return a fresh in-memory cache gateway."""
    return FakeCacheGateway()


@pytest.fixture()
def fake_cache_down() -> FakeCacheGateway:
    """Return a cache gateway that simulates an unavailable Redis."""
    return FakeCacheGateway(available=False)


@pytest.fixture()
def test_settings() -> Settings:
    """Return Settings pre-populated with safe test values."""
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture()
def app_with_fake_cache(fake_cache: FakeCacheGateway) -> FastAPI:
    """Return the FastAPI app with the cache gateway swapped for a fake."""
    application = create_app()
    application.dependency_overrides[get_cache_gateway] = lambda: fake_cache
    return application


@pytest.fixture()
def client(app_with_fake_cache: FastAPI) -> TestClient:
    """Return a synchronous TestClient backed by the fake-cache app."""
    return TestClient(app_with_fake_cache, raise_server_exceptions=False)
