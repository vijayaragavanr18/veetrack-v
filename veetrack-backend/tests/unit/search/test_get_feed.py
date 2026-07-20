"""Unit tests: GetFeed use case — Fast/Cold path decision, cursor pagination,
sanitise helper, serialisation round-trip.

No infrastructure imports — all I/O is stubbed via in-memory fakes.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.application.use_cases.search.feed_types import (
    ArticleSummaryItem,
    StoryPayload,
    feed_cache_key,
)
from app.application.use_cases.search.get_feed import GetFeed, _sanitise, serialise_payloads

# ---------------------------------------------------------------------------
# Fakes / stubs
# ---------------------------------------------------------------------------


class _FakeCache:
    def __init__(self, data: dict[str, bytes] | None = None) -> None:
        self._data: dict[str, bytes] = data or {}

    async def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def ping(self) -> bool:
        return True


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, task_name: str, kwargs: dict[str, Any], queue: str = "ingestion") -> None:
        self.calls.append({"task": task_name, "kwargs": kwargs, "queue": queue})


def _make_story(story_id: str, entity_id: str = "eid-1", title: str = "Story") -> StoryPayload:
    return StoryPayload(
        id=story_id,
        title=title,
        status="active",
        risk_level="low",
        primary_entity_id=entity_id,
        entity_name="Tesla",
        article_count=3,
        articles=[
            ArticleSummaryItem(
                id=f"a-{story_id}",
                headline="Test headline",
                publisher="Reuters",
                published_at="2026-07-16T00:00:00",
                sentiment_label="neutral",
            )
        ],
        updated_at="2026-07-16T00:00:00",
    )


def _cached_payload(stories: list[StoryPayload], entity_id: str) -> dict[str, bytes]:
    return {feed_cache_key(entity_id): serialise_payloads(stories)}


# DB query stub — returns entity rows on alias lookup, then no articles by default
async def _db_returns_entity(entity_id: str = "eid-1", name: str = "Tesla") -> list[dict]:
    return [{"id": entity_id, "canonical_name": name}]


def _make_db_stub(
    entity_rows: list[dict] | None = None,
    story_rows: list[dict] | None = None,
    article_rows: list[dict] | None = None,
) -> Any:
    async def _stub(sql: str, params: dict[str, Any]) -> list[dict]:
        if "entity_aliases" in sql:
            return entity_rows or []
        # Article preview query is uniquely identified by the ANY(:sids) filter
        if "ANY(:sids)" in sql:
            return article_rows or []
        # Story queries (both entity-based and trigram)
        if "stories" in sql:
            return story_rows or []
        return []

    return _stub


# ---------------------------------------------------------------------------
# Fast Path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fast_path_returns_cached_stories() -> None:
    stories = [_make_story("s1"), _make_story("s2"), _make_story("s3")]
    cache = _FakeCache(_cached_payload(stories, "eid-1"))
    dispatcher = _FakeDispatcher()

    db = _make_db_stub(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("tesla")

    assert page.path == "fast"
    assert len(page.stories) == 3
    assert page.entity_id == "eid-1"
    assert page.entity_name == "Tesla"
    # Fast path does not dispatch anything
    assert dispatcher.calls == []


@pytest.mark.asyncio
async def test_fast_path_cursor_pagination() -> None:
    stories = [_make_story(f"s{i}") for i in range(5)]
    cache = _FakeCache(_cached_payload(stories, "eid-1"))
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)

    # First page (limit=2)
    page1 = await use_case.execute("tesla", limit=2)
    assert page1.path == "fast"
    assert len(page1.stories) == 2
    assert page1.next_cursor == "s1"

    # Second page from cursor
    page2 = await use_case.execute("tesla", cursor="s1", limit=2)
    assert page2.path == "fast"
    assert [s.id for s in page2.stories] == ["s2", "s3"]
    assert page2.next_cursor == "s3"

    # Last page — no next cursor
    page3 = await use_case.execute("tesla", cursor="s3", limit=2)
    assert page3.path == "fast"
    assert len(page3.stories) == 1
    assert page3.next_cursor is None


@pytest.mark.asyncio
async def test_fast_path_unknown_cursor_starts_from_beginning() -> None:
    """An unknown cursor value should fall back to position 0."""
    stories = [_make_story("s1"), _make_story("s2")]
    cache = _FakeCache(_cached_payload(stories, "eid-1"))
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)

    page = await use_case.execute("tesla", cursor="does-not-exist", limit=10)
    assert page.path == "fast"
    assert len(page.stories) == 2


# ---------------------------------------------------------------------------
# Cold Path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cold_path_known_entity_cache_miss_dispatches_build() -> None:
    cache = _FakeCache()  # empty cache
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(
        entity_rows=[{"id": "eid-1", "canonical_name": "Tesla"}],
        story_rows=[],
    )
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("tesla")

    assert page.path == "cold"
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0]["task"] == "tasks.search.build_feed_cache.run"
    assert dispatcher.calls[0]["kwargs"] == {"entity_id": "eid-1"}


@pytest.mark.asyncio
async def test_cold_path_unknown_keyword_dispatches_track() -> None:
    cache = _FakeCache()
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(entity_rows=[], story_rows=[])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("unknown keyword")

    assert page.path == "cold"
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0]["task"] == "tasks.search.track_new_entity.run"
    assert dispatcher.calls[0]["kwargs"] == {"keyword": "unknown keyword"}


@pytest.mark.asyncio
async def test_cold_path_empty_after_sanitise_returns_empty() -> None:
    """Keyword that strips to empty should return an empty page without querying stories."""
    cache = _FakeCache()
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(entity_rows=[])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("!!!")  # all non-word chars

    assert page.stories == []


@pytest.mark.asyncio
async def test_cold_path_next_cursor_set_when_full_page() -> None:
    cache = _FakeCache()
    dispatcher = _FakeDispatcher()
    from datetime import UTC, datetime

    now = datetime(2026, 7, 16, tzinfo=UTC)
    story_rows = [
        {
            "id": f"s{i}",
            "title": f"Story {i}",
            "status": "active",
            "risk_level": "low",
            "primary_entity_id": "eid-1",
            "updated_at": now,
            "entity_name": "Tesla",
            "article_count": 1,
        }
        for i in range(3)
    ]
    db = _make_db_stub(entity_rows=[], story_rows=story_rows, article_rows=[])
    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("tesla news", limit=3)

    assert page.next_cursor == "s2"


# ---------------------------------------------------------------------------
# _sanitise helper
# ---------------------------------------------------------------------------


def test_sanitise_removes_special_chars() -> None:
    assert _sanitise("Hello!!! <world>") == "Hello world"


def test_sanitise_truncates_long_input() -> None:
    long_str = "a" * 300
    assert len(_sanitise(long_str)) == 200


def test_sanitise_preserves_hyphen_and_spaces() -> None:
    result = _sanitise("Elon-Musk Tesla")
    assert result == "Elon-Musk Tesla"


def test_sanitise_empty_string() -> None:
    assert _sanitise("") == ""


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------


def test_serialise_deserialise_round_trip() -> None:
    from app.application.use_cases.search.feed_types import InsightItem, RecommendationItem
    from app.application.use_cases.search.get_feed import _deserialise_payloads

    story = StoryPayload(
        id="s1",
        title="Test",
        status="active",
        risk_level="medium",
        primary_entity_id="eid-1",
        entity_name="Apple",
        article_count=2,
        articles=[
            ArticleSummaryItem(
                id="a1",
                headline="Headline",
                publisher="BBC",
                published_at="2026-07-01T00:00:00",
                sentiment_label="positive",
            )
        ],
        insight=InsightItem(
            what_happened="X happened",
            why_happened="Because Y",
            model_used="claude-haiku",
        ),
        cluster_member_ids=["a1", "a2"],
        recommendations=[
            RecommendationItem(
                id="r1",
                audience="pr",
                recommendation_text="Issue a statement",
                risk_level="low",
                confidence_score=0.9,
                needs_human_review=False,
            )
        ],
        updated_at="2026-07-16T00:00:00",
    )

    raw = serialise_payloads([story])
    restored = _deserialise_payloads(raw)
    assert len(restored) == 1
    r = restored[0]
    assert r.id == "s1"
    assert r.insight is not None
    assert r.insight.what_happened == "X happened"
    assert len(r.recommendations) == 1
    assert r.recommendations[0].audience == "pr"
    assert len(r.cluster_member_ids) == 2
