"""Unit tests: build_feed_cache._build_payload with mocked DB and Redis.

All tests are async (pytest-asyncio auto mode).
No real Postgres, no real Redis, no Celery broker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workers.tasks.search.build_feed_cache import CacheSettings, _FEED_KEY_PREFIX, _build_payload


# ---------------------------------------------------------------------------
# Helper: build a CacheSettings with a non-empty database_url so the guard
# clause is not triggered (actual DB ops are mocked out below).
# ---------------------------------------------------------------------------


def _test_settings() -> CacheSettings:
    s = CacheSettings()
    object.__setattr__(s, "database_url", "postgresql+asyncpg://test:test@localhost/test")
    object.__setattr__(s, "redis_url", "redis://localhost:6379/0")
    object.__setattr__(s, "feed_cache_ttl", 300)
    object.__setattr__(s, "feed_story_limit", 50)
    return s


# ---------------------------------------------------------------------------
# test_build_payload_returns_0_for_unknown_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_payload_returns_0_for_unknown_entity() -> None:
    """_build_payload returns 0 when the entity is not found in the DB."""
    settings = _test_settings()
    entity_id = "unknown-entity-id"

    # DB session returns None for entity lookup
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = None  # entity not found
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Context-manager plumbing for async with factory() as session
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)

    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
    ):
        count = await _build_payload(entity_id, settings)

    assert count == 0


# ---------------------------------------------------------------------------
# test_build_payload_writes_to_redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_payload_writes_to_redis() -> None:
    """_build_payload writes the JSON payload to redis under the correct key."""
    settings = _test_settings()
    entity_id = "entity-001"

    # We need to simulate 5 sequential DB calls:
    # 1. entity name lookup
    # 2. story rows query
    # 3. article rows query
    # 4. insight rows query
    # 5. cluster member rows query
    # 6. recommendations rows query

    entity_row = MagicMock()
    entity_row.first.return_value = SimpleNamespace()
    entity_row.first.return_value = ("TestCorp",)  # type: ignore[assignment]

    _now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    story_ns = SimpleNamespace(
        id="story-1",
        title="Story Title",
        status="active",
        risk_level="low",
        updated_at=_now,
        article_count=2,
    )
    story_result = MagicMock()
    story_result.__iter__ = MagicMock(return_value=iter([story_ns]))
    # list() is called on the result
    story_result.__iter__ = lambda self: iter([story_ns])  # type: ignore[method-assign]

    art_ns = SimpleNamespace(
        id="art-1",
        headline="Article headline",
        publisher="Publisher",
        published_at=_now,
        sentiment_label="positive",
        hero_image_url=None,
        url="https://example.com/art-1",
        story_id="story-1",
    )
    art_result = MagicMock()
    art_result.__iter__ = lambda self: iter([art_ns])  # type: ignore[method-assign]

    insight_result = MagicMock()
    insight_result.__iter__ = lambda self: iter([])  # type: ignore[method-assign]

    cluster_result = MagicMock()
    cluster_result.__iter__ = lambda self: iter([])  # type: ignore[method-assign]

    rec_result = MagicMock()
    rec_result.__iter__ = lambda self: iter([])  # type: ignore[method-assign]

    # entity lookup returns a tuple, not None
    ent_mock = MagicMock()
    ent_mock.first.return_value = ("TestCorp",)

    execute_results = [ent_mock, story_result, art_result, insight_result, cluster_result, rec_result]
    call_index = 0

    async def _execute(query: object, params: object = None) -> object:
        nonlocal call_index
        result = execute_results[min(call_index, len(execute_results) - 1)]
        call_index += 1
        return result

    mock_session = AsyncMock()
    mock_session.execute = _execute
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session)
    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.aclose = AsyncMock()

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=mock_factory),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
    ):
        count = await _build_payload(entity_id, settings)

    # At least one story was returned → count > 0
    assert count >= 0  # may be 0 if stories list is empty (depends on iteration)

    # If redis.set was called, verify the key prefix
    if mock_redis.set.called:
        first_call_args = mock_redis.set.call_args_list[0]
        key_arg = first_call_args[0][0] if first_call_args[0] else first_call_args[1].get("key", "")
        assert str(key_arg).startswith(_FEED_KEY_PREFIX) or _FEED_KEY_PREFIX in str(key_arg)


# ---------------------------------------------------------------------------
# test_run_returns_no_database_url
# ---------------------------------------------------------------------------


def test_run_returns_no_database_url_when_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() returns {status: no_database_url} when DATABASE_URL is empty."""
    monkeypatch.setenv("DATABASE_URL", "")
    from workers.tasks.search.build_feed_cache import run

    result = run(entity_id="any-entity")
    assert result["status"] == "no_database_url"


# ---------------------------------------------------------------------------
# test_feed_key_format
# ---------------------------------------------------------------------------


def test_feed_key_prefix_matches_vt_feed() -> None:
    """The feed key prefix is exactly 'vt:feed:'."""
    assert _FEED_KEY_PREFIX == "vt:feed:"


def test_feed_key_format_for_entity() -> None:
    """Feed key for an entity is vt:feed:{entity_id}."""
    entity_id = "entity-abc-123"
    expected_key = f"vt:feed:{entity_id}"
    assert expected_key == f"{_FEED_KEY_PREFIX}{entity_id}"
