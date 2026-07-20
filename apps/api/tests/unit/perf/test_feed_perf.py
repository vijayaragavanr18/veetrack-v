"""Phase 27 — GetFeed use case: alias micro-cache and cold-result cache tests.

These tests verify the Phase 27 caching optimisations:
1. Alias micro-cache eliminates DB round-trip on repeated Fast Path requests.
2. Cold-result micro-cache suppresses repeated DB hits within its TTL.
3. Alias cache miss populates the cache correctly (entity found).
4. Alias cache miss populates the cache for an unknown keyword (empty entity_id).
5. Warm alias + warm feed = zero DB queries (pure Redis Fast Path).

No infrastructure imports — all I/O is via in-memory fakes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.search.feed_types import (
    ALIAS_CACHE_TTL,
    COLD_RESULT_CACHE_TTL,
    ArticleSummaryItem,
    StoryPayload,
    feed_cache_key,
)
from app.application.use_cases.search.get_feed import GetFeed, serialise_payloads

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _TrackedCache:
    """Cache that tracks all get/set calls for assertion."""

    def __init__(self, initial: dict[str, bytes] | None = None) -> None:
        self._data: dict[str, bytes] = initial or {}
        self.gets: list[str] = []
        self.sets: list[tuple[str, int]] = []  # (key, ttl)

    async def get(self, key: str) -> bytes | None:
        self.gets.append(key)
        return self._data.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        self.sets.append((key, ttl_seconds))
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def ping(self) -> bool:
        return True


class _CountingDB:
    """DB query stub that counts invocations per query type."""

    def __init__(
        self,
        entity_rows: list[dict] | None = None,
        story_rows: list[dict] | None = None,
        article_rows: list[dict] | None = None,
    ) -> None:
        self._entity_rows = entity_rows or []
        self._story_rows = story_rows or []
        self._article_rows = article_rows or []
        self.alias_call_count = 0
        self.story_call_count = 0
        self.article_call_count = 0

    async def __call__(self, sql: str, params: dict[str, Any]) -> list[dict]:
        if "entity_aliases" in sql:
            self.alias_call_count += 1
            return self._entity_rows
        if "ANY(:sids)" in sql:
            self.article_call_count += 1
            return self._article_rows
        if "stories" in sql:
            self.story_call_count += 1
            return self._story_rows
        return []


class _FakeDispatcher:
    def send(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        pass


def _story(story_id: str, entity_id: str = "eid-1") -> StoryPayload:
    return StoryPayload(
        id=story_id, title="T", status="active", risk_level="low",
        primary_entity_id=entity_id, entity_name="Tesla",
        article_count=1,
        articles=[ArticleSummaryItem(
            id=f"a-{story_id}", headline="H", publisher="P",
            published_at="2026-07-16T00:00:00", sentiment_label="neutral",
        )],
        updated_at="2026-07-16T00:00:00",
    )


def _alias_cache_key(keyword: str) -> str:
    return f"vt:alias:{keyword.lower()}"


# ---------------------------------------------------------------------------
# Alias micro-cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alias_cache_populated_on_first_miss() -> None:
    """First request hits DB; alias is then stored in cache."""
    cache = _TrackedCache()
    db = _CountingDB(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    await use_case.execute("Tesla")

    assert db.alias_call_count == 1
    # The alias key should now be in cache
    stored = cache._data.get(_alias_cache_key("Tesla"))
    assert stored is not None
    assert b"eid-1" in stored
    assert b"Tesla" in stored

    # Check TTL recorded
    alias_set = [k for k, ttl in cache.sets if "vt:alias:" in k]
    assert len(alias_set) == 1
    _, ttl = next((k, t) for k, t in cache.sets if "vt:alias:" in k)
    assert ttl == ALIAS_CACHE_TTL


@pytest.mark.asyncio
async def test_alias_cache_hit_skips_db() -> None:
    """Warm alias cache → no DB call for alias lookup."""
    # Pre-populate alias cache
    alias_key = _alias_cache_key("Tesla")
    initial = {alias_key: b"eid-1\x00Tesla"}
    # Also pre-populate feed cache so Fast Path completes
    stories = [_story("s1")]
    initial[feed_cache_key("eid-1")] = serialise_payloads(stories)

    cache = _TrackedCache(initial=initial)
    db = _CountingDB(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    page = await use_case.execute("Tesla")

    # Zero DB calls — alias and feed both from cache
    assert db.alias_call_count == 0
    assert db.story_call_count == 0
    assert page.path == "fast"
    assert len(page.stories) == 1


@pytest.mark.asyncio
async def test_alias_cache_miss_unknown_keyword_stored_as_empty() -> None:
    """Unknown keyword (no entity match) stores empty entity_id in cache."""
    cache = _TrackedCache()
    db = _CountingDB(entity_rows=[])  # no match
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    await use_case.execute("unknownword")

    assert db.alias_call_count == 1
    stored = cache._data.get(_alias_cache_key("unknownword"))
    assert stored is not None
    # entity_id part is empty
    parts = stored.decode().split("\x00", 1)
    assert parts[0] == ""  # no entity_id
    assert parts[1] == "unknownword"  # entity_name falls back to keyword


@pytest.mark.asyncio
async def test_second_request_uses_alias_cache() -> None:
    """Second identical request uses alias cache, not DB."""
    cache = _TrackedCache()
    db = _CountingDB(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    dispatcher = _FakeDispatcher()
    # Pre-populate feed cache too so we stay on fast path
    stories = [_story("s1")]
    cache._data[feed_cache_key("eid-1")] = serialise_payloads(stories)

    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)

    # First request — populates alias cache
    await use_case.execute("Tesla")
    assert db.alias_call_count == 1

    # Second request — alias cache hit
    await use_case.execute("Tesla")
    assert db.alias_call_count == 1  # unchanged


# ---------------------------------------------------------------------------
# Cold-result micro-cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cold_result_cache_populated_on_first_cold_hit() -> None:
    """First Cold Path query populates the cold-result cache."""
    from datetime import UTC, datetime

    cache = _TrackedCache()
    now = datetime(2026, 7, 16, tzinfo=UTC)
    story_rows = [{
        "id": "s1", "title": "Story", "status": "active", "risk_level": "low",
        "primary_entity_id": "eid-1", "updated_at": now,
        "entity_name": "Tesla", "article_count": 1,
    }]
    db = _CountingDB(entity_rows=[], story_rows=story_rows)
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    page = await use_case.execute("new-keyword", limit=10)

    assert page.path == "cold"
    assert db.story_call_count == 1

    # Cold result key should be in cache
    cold_keys = [k for k in cache._data if k.startswith("vt:cold:")]
    assert len(cold_keys) == 1
    # Verify TTL
    cold_ttls = [t for k, t in cache.sets if k.startswith("vt:cold:")]
    assert cold_ttls and cold_ttls[0] == COLD_RESULT_CACHE_TTL


@pytest.mark.asyncio
async def test_cold_result_cache_hit_skips_db() -> None:
    """Second Cold Path request within TTL uses cache, no DB stories query."""
    from datetime import UTC, datetime

    now = datetime(2026, 7, 16, tzinfo=UTC)
    story_rows = [{
        "id": "s1", "title": "Story", "status": "active", "risk_level": "low",
        "primary_entity_id": "eid-1", "updated_at": now,
        "entity_name": "Tesla", "article_count": 1,
    }]
    # Pre-populate alias cache (empty entity_id) and cold-result cache
    cache = _TrackedCache()
    cache._data[_alias_cache_key("new-keyword")] = b"\x00new-keyword"
    # Manually build what would be in the cold-result cache
    initial_stories = [_story("s1")]
    cold_key = "vt:cold:new-keyword::10"
    cache._data[cold_key] = serialise_payloads(initial_stories)

    db = _CountingDB(entity_rows=[], story_rows=story_rows)
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    page = await use_case.execute("new-keyword", limit=10)

    # DB story query should NOT have been called
    assert db.story_call_count == 0
    assert page.path == "cold"
    assert len(page.stories) == 1


@pytest.mark.asyncio
async def test_cold_result_not_cached_when_empty() -> None:
    """Empty cold result should not be stored (would mask future results)."""
    cache = _TrackedCache()
    db = _CountingDB(entity_rows=[], story_rows=[])
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    await use_case.execute("noresult")

    cold_keys = [k for k in cache._data if k.startswith("vt:cold:")]
    assert cold_keys == []


# ---------------------------------------------------------------------------
# Fast Path cache count (regression: must be exactly 2 Redis ops)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fast_path_warm_uses_exactly_two_redis_ops() -> None:
    """Warm alias + warm feed = 2 Redis GET calls, 0 DB calls."""
    alias_key = _alias_cache_key("Tesla")
    stories = [_story("s1")]
    initial = {
        alias_key: b"eid-1\x00Tesla",
        feed_cache_key("eid-1"): serialise_payloads(stories),
    }
    cache = _TrackedCache(initial=initial)
    db = _CountingDB()
    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=db)

    page = await use_case.execute("Tesla")

    assert page.path == "fast"
    # The two GETs must be the alias key and the feed key
    assert _alias_cache_key("Tesla") in cache.gets
    assert feed_cache_key("eid-1") in cache.gets
    # Exactly these two, nothing else
    redis_gets = [k for k in cache.gets if k.startswith("vt:")]
    assert len(redis_gets) == 2
    # Zero DB
    assert db.alias_call_count == 0
    assert db.story_call_count == 0


# ---------------------------------------------------------------------------
# TTL constant sanity
# ---------------------------------------------------------------------------


def test_feed_cache_ttl_increased_for_phase_27() -> None:
    from app.application.use_cases.search.feed_types import FEED_CACHE_TTL

    # Phase 27 raised this from 300 s to 600 s — verify the change landed.
    assert FEED_CACHE_TTL == 600, (
        f"FEED_CACHE_TTL should be 600 (10 min) but got {FEED_CACHE_TTL}. "
        "Phase 27 tuning decision: pipeline runs every 15 min, 10 min TTL = at most one cycle stale."
    )


def test_alias_cache_ttl_is_60s() -> None:
    assert ALIAS_CACHE_TTL == 60


def test_cold_result_cache_ttl_is_30s() -> None:
    assert COLD_RESULT_CACHE_TTL == 30
