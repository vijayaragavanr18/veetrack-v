"""Unit tests: workers RssClient — feed parsing and error handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fakeredis
import pytest

from connectors.rss import (
    RssClient,
    _entry_to_article,
    _host_source_id,
    _parse_entry_date,
)

SOURCE_ID = "rss-workers-test"
SINCE = datetime(2020, 1, 1, tzinfo=UTC)  # far past — all test entries should pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    title: str = "Entry Title",
    link: str = "https://example.com/article",
    entry_id: str = "https://example.com/article",
    summary: str = "Summary text",
    published_parsed: tuple | None = (2024, 12, 10, 10, 0, 0, 0, 0, 0),
) -> MagicMock:
    e = MagicMock()
    e.title = title
    e.link = link
    e.id = entry_id
    e.summary = summary
    e.published_parsed = published_parsed
    e.updated_parsed = None
    e.content = []
    e.enclosures = []
    return e


def _make_parsed(entries: list, *, bozo: bool = False, feed_title: str = "Workers Feed") -> MagicMock:
    p = MagicMock()
    p.get = lambda key, default=None: (
        entries if key == "entries" else (bozo if key == "bozo" else default)
    )
    p.feed = MagicMock()
    p.feed.title = feed_title
    return p


# ---------------------------------------------------------------------------
# _host_source_id
# ---------------------------------------------------------------------------

def test_host_source_id_extracts_hostname() -> None:
    hid = _host_source_id("src", "https://feeds.news.com/rss")
    assert "feeds.news.com" in hid


def test_host_source_id_different_sources_differ() -> None:
    a = _host_source_id("src1", "https://example.com/feed")
    b = _host_source_id("src2", "https://example.com/feed")
    assert a != b


# ---------------------------------------------------------------------------
# _parse_entry_date
# ---------------------------------------------------------------------------

def test_parse_entry_date_uses_published() -> None:
    e = MagicMock()
    e.published_parsed = (2024, 3, 15, 8, 0, 0, 0, 0, 0)
    e.updated_parsed = None
    dt = _parse_entry_date(e)
    assert dt.year == 2024 and dt.month == 3


def test_parse_entry_date_falls_back_to_updated() -> None:
    e = MagicMock()
    e.published_parsed = None
    e.updated_parsed = (2025, 1, 20, 0, 0, 0, 0, 0, 0)
    dt = _parse_entry_date(e)
    assert dt.year == 2025


def test_parse_entry_date_none_returns_now() -> None:
    e = MagicMock()
    e.published_parsed = None
    e.updated_parsed = None
    dt = _parse_entry_date(e)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _entry_to_article
# ---------------------------------------------------------------------------

def test_entry_to_article_maps_fields() -> None:
    entry = _make_entry()
    article = _entry_to_article(entry, "https://example.com/feed", "My Site")
    assert article is not None
    assert article.headline == "Entry Title"
    assert article.publisher == "My Site"
    assert article.metadata_json["feed_url"] == "https://example.com/feed"


def test_entry_to_article_missing_title_returns_none() -> None:
    entry = _make_entry(title=None)  # type: ignore[arg-type]
    assert _entry_to_article(entry, "https://example.com/feed", "Feed") is None


def test_entry_to_article_missing_link_returns_none() -> None:
    entry = _make_entry(link=None, entry_id=None)  # type: ignore[arg-type]
    assert _entry_to_article(entry, "https://example.com/feed", "Feed") is None


def test_entry_to_article_image_enclosure() -> None:
    enc = MagicMock()
    enc.type = "image/png"
    enc.href = "https://example.com/img.png"
    entry = _make_entry()
    entry.enclosures = [enc]
    article = _entry_to_article(entry, "https://example.com/feed", "Feed")
    assert article is not None
    assert article.hero_image_url == "https://example.com/img.png"


# ---------------------------------------------------------------------------
# RssClient.fetch
# ---------------------------------------------------------------------------

@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.mark.asyncio
async def test_fetch_returns_articles(redis: fakeredis.FakeRedis) -> None:
    client = RssClient(SOURCE_ID, ["https://example.com/feed"], redis)
    with patch("feedparser.parse") as mock:
        mock.return_value = _make_parsed([_make_entry()])
        articles = await client.fetch(SINCE)
    assert len(articles) == 1
    assert articles[0].headline == "Entry Title"


@pytest.mark.asyncio
async def test_fetch_filters_old_articles(redis: fakeredis.FakeRedis) -> None:
    old = _make_entry(published_parsed=(2020, 1, 1, 0, 0, 0, 0, 0, 0))
    client = RssClient(SOURCE_ID, ["https://example.com/feed"], redis)
    with patch("feedparser.parse") as mock:
        mock.return_value = _make_parsed([old])
        articles = await client.fetch(since=datetime(2024, 1, 1, tzinfo=UTC))
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_malformed_feed_does_not_raise(redis: fakeredis.FakeRedis) -> None:
    client = RssClient(SOURCE_ID, ["https://example.com/feed"], redis)
    with patch("feedparser.parse") as mock:
        p = _make_parsed([_make_entry()], bozo=True)
        mock.return_value = p
        articles = await client.fetch(SINCE)
    # bozo feed → warning logged, no exception raised
    assert isinstance(articles, list)


@pytest.mark.asyncio
async def test_fetch_network_error_returns_empty(redis: fakeredis.FakeRedis) -> None:
    client = RssClient(SOURCE_ID, ["https://example.com/feed"], redis)
    with patch("feedparser.parse", side_effect=OSError("No route to host")):
        articles = await client.fetch(SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_multiple_feeds_aggregated(redis: fakeredis.FakeRedis) -> None:
    client = RssClient(
        SOURCE_ID,
        ["https://feed-a.com/rss", "https://feed-b.com/rss"],
        redis,
    )
    entry_a = _make_entry(title="A", link="https://feed-a.com/1", entry_id="a1")
    entry_b = _make_entry(title="B", link="https://feed-b.com/1", entry_id="b1")

    def _fake(url: str) -> MagicMock:
        return _make_parsed([entry_a] if "feed-a" in url else [entry_b])

    with patch("feedparser.parse", side_effect=_fake):
        articles = await client.fetch(SINCE)
    assert len(articles) == 2


@pytest.mark.asyncio
async def test_fetch_no_feeds_returns_empty(redis: fakeredis.FakeRedis) -> None:
    client = RssClient(SOURCE_ID, [], redis)
    articles = await client.fetch(SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_per_host_limiters_are_distinct(redis: fakeredis.FakeRedis) -> None:
    """Two feeds on different hosts should use separate rate-limit buckets."""
    client = RssClient(
        SOURCE_ID,
        ["https://host-a.com/feed", "https://host-b.com/feed"],
        redis,
    )
    entry = _make_entry()
    with patch("feedparser.parse", return_value=_make_parsed([entry])):
        await client.fetch(SINCE)
    # Two distinct limiters created — one per host
    assert len(client._limiters) == 2
    keys = list(client._limiters.keys())
    assert keys[0] != keys[1]
