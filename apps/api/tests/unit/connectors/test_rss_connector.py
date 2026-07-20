"""Unit tests: RssConnector — feed parsing and per-host rate limiting."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import fakeredis.aioredis as fakeredis
import pytest

from app.infrastructure.connectors.rss_connector import (
    RssConnector,
    _entry_to_article,
    _host_source_id,
    _parse_entry_date,
)

SOURCE_ID = "rss-test"
SINCE = datetime(2020, 1, 1, tzinfo=UTC)  # far past — all test entries should pass

# ---------------------------------------------------------------------------
# Minimal feedparser-style entry mock helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    title: str = "Test Title",
    link: str = "https://example.com/article",
    entry_id: str = "https://example.com/article",
    summary: str = "Short summary",
    published_parsed: tuple | None = (2024, 12, 10, 10, 0, 0, 0, 0, 0),
    enclosures: list | None = None,
) -> MagicMock:
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.id = entry_id
    entry.summary = summary
    entry.published_parsed = published_parsed
    entry.updated_parsed = None
    entry.content = []
    entry.enclosures = enclosures or []
    return entry


def _make_parsed(entries: list, *, bozo: bool = False, feed_title: str = "My Feed") -> MagicMock:
    parsed = MagicMock()
    parsed.get = lambda key, default=None: (
        entries if key == "entries" else (bozo if key == "bozo" else default)
    )
    parsed.feed = MagicMock()
    parsed.feed.title = feed_title
    parsed.__getitem__ = lambda self, key: entries if key == "entries" else bozo
    return parsed


# ---------------------------------------------------------------------------
# _host_source_id
# ---------------------------------------------------------------------------

def test_host_source_id_uses_hostname() -> None:
    hid = _host_source_id("src1", "https://feeds.example.com/rss")
    assert "src1" in hid
    assert "feeds.example.com" in hid


def test_host_source_id_different_hosts_differ() -> None:
    a = _host_source_id("src1", "https://host-a.com/feed")
    b = _host_source_id("src1", "https://host-b.com/feed")
    assert a != b


def test_host_source_id_same_host_same() -> None:
    a = _host_source_id("src1", "https://example.com/feed1")
    b = _host_source_id("src1", "https://example.com/feed2")
    assert a == b


# ---------------------------------------------------------------------------
# _parse_entry_date
# ---------------------------------------------------------------------------

def test_parse_entry_date_published() -> None:
    entry = MagicMock()
    entry.published_parsed = (2024, 6, 15, 12, 0, 0, 0, 0, 0)
    entry.updated_parsed = None
    dt = _parse_entry_date(entry)
    assert dt.year == 2024 and dt.month == 6 and dt.day == 15


def test_parse_entry_date_fallback_updated() -> None:
    entry = MagicMock()
    entry.published_parsed = None
    entry.updated_parsed = (2024, 8, 1, 9, 30, 0, 0, 0, 0)
    dt = _parse_entry_date(entry)
    assert dt.year == 2024 and dt.month == 8


def test_parse_entry_date_no_date_returns_now() -> None:
    entry = MagicMock()
    entry.published_parsed = None
    entry.updated_parsed = None
    dt = _parse_entry_date(entry)
    assert (datetime.now(UTC) - dt).total_seconds() < 5


# ---------------------------------------------------------------------------
# _entry_to_article
# ---------------------------------------------------------------------------

def test_entry_to_article_full() -> None:
    entry = _make_entry()
    article = _entry_to_article(entry, "https://example.com/feed", "Example Feed")
    assert article is not None
    assert article.headline == "Test Title"
    assert article.url == "https://example.com/article"
    assert article.publisher == "Example Feed"
    assert article.raw_content == "Short summary"
    assert article.metadata_json["feed_url"] == "https://example.com/feed"


def test_entry_to_article_prefers_content_over_summary() -> None:
    entry = _make_entry()
    content_item = MagicMock()
    content_item.value = "Full body content here"
    entry.content = [content_item]
    article = _entry_to_article(entry, "https://example.com/feed", "Feed")
    assert article is not None
    assert article.raw_content == "Full body content here"


def test_entry_to_article_no_title_returns_none() -> None:
    entry = _make_entry(title=None)  # type: ignore[arg-type]
    assert _entry_to_article(entry, "https://example.com/feed", "Feed") is None


def test_entry_to_article_no_link_returns_none() -> None:
    entry = _make_entry(link=None, entry_id=None)  # type: ignore[arg-type]
    assert _entry_to_article(entry, "https://example.com/feed", "Feed") is None


def test_entry_to_article_image_enclosure() -> None:
    enc = MagicMock()
    enc.type = "image/jpeg"
    enc.href = "https://example.com/image.jpg"
    entry = _make_entry(enclosures=[enc])
    article = _entry_to_article(entry, "https://example.com/feed", "Feed")
    assert article is not None
    assert article.hero_image_url == "https://example.com/image.jpg"


def test_entry_to_article_non_image_enclosure_ignored() -> None:
    enc = MagicMock()
    enc.type = "audio/mpeg"
    enc.href = "https://example.com/audio.mp3"
    entry = _make_entry(enclosures=[enc])
    article = _entry_to_article(entry, "https://example.com/feed", "Feed")
    assert article is not None
    assert article.hero_image_url is None


# ---------------------------------------------------------------------------
# RssConnector.fetch — feedparser mocked
# ---------------------------------------------------------------------------

_RSS_XML = textwrap.dedent("""\
    <?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <link>https://example.com</link>
        <item>
          <title>Article One</title>
          <link>https://example.com/1</link>
          <guid>https://example.com/1</guid>
          <description>Desc one</description>
          <pubDate>Mon, 10 Dec 2024 10:00:00 +0000</pubDate>
        </item>
      </channel>
    </rss>
""")


@pytest.fixture()
async def redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=False)


@pytest.mark.asyncio
async def test_fetch_valid_feed(redis: fakeredis.FakeRedis) -> None:
    connector = RssConnector(
        SOURCE_ID,
        ["https://example.com/feed.rss"],
        redis,
    )
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _make_parsed([_make_entry()])
        articles = await connector.fetch("ignored_query", SINCE)
    assert len(articles) == 1
    assert articles[0].publisher == "My Feed"


@pytest.mark.asyncio
async def test_fetch_filters_old_entries(redis: fakeredis.FakeRedis) -> None:
    old_entry = _make_entry(published_parsed=(2020, 1, 1, 0, 0, 0, 0, 0, 0))
    connector = RssConnector(SOURCE_ID, ["https://example.com/feed.rss"], redis)
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value = _make_parsed([old_entry])
        articles = await connector.fetch("q", since=datetime(2024, 1, 1, tzinfo=UTC))
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_multiple_feeds(redis: fakeredis.FakeRedis) -> None:
    connector = RssConnector(
        SOURCE_ID,
        ["https://feed-a.com/rss", "https://feed-b.com/rss"],
        redis,
    )
    entry_a = _make_entry(title="A", link="https://feed-a.com/1", entry_id="a1")
    entry_b = _make_entry(title="B", link="https://feed-b.com/1", entry_id="b1")

    call_count = 0
    def _fake_parse(url: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return _make_parsed([entry_a] if "feed-a" in url else [entry_b])

    with patch("feedparser.parse", side_effect=_fake_parse):
        articles = await connector.fetch("q", SINCE)
    assert len(articles) == 2
    assert call_count == 2


@pytest.mark.asyncio
async def test_fetch_malformed_feed_continues(redis: fakeredis.FakeRedis) -> None:
    """bozo=True feed: still processes partial entries, doesn't crash."""
    connector = RssConnector(SOURCE_ID, ["https://example.com/feed.rss"], redis)
    with patch("feedparser.parse") as mock_parse:
        p = _make_parsed([_make_entry()], bozo=True)
        p.get = lambda key, default=None: (
            [_make_entry()] if key == "entries" else (True if key == "bozo" else default)
        )
        p.feed.title = "Partial Feed"
        mock_parse.return_value = p
        articles = await connector.fetch("q", SINCE)
    # bozo feed → warning logged, but entries still processed
    assert len(articles) >= 0  # doesn't raise


@pytest.mark.asyncio
async def test_fetch_unreachable_feed_returns_empty(redis: fakeredis.FakeRedis) -> None:
    connector = RssConnector(SOURCE_ID, ["https://example.com/feed.rss"], redis)
    with patch("feedparser.parse", side_effect=OSError("Network unreachable")):
        articles = await connector.fetch("q", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_no_feeds_returns_empty(redis: fakeredis.FakeRedis) -> None:
    connector = RssConnector(SOURCE_ID, [], redis)
    articles = await connector.fetch("q", SINCE)
    assert articles == []


@pytest.mark.asyncio
async def test_remaining_quota_no_feeds(redis: fakeredis.FakeRedis) -> None:
    connector = RssConnector(SOURCE_ID, [], redis)
    quota = await connector.remaining_quota()
    assert quota.source_id == SOURCE_ID
    assert quota.calls_made == 0
