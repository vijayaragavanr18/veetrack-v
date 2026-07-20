"""RSS/Atom source connector.

Parses one or more feed URLs from source.config_json["feed_urls"] using feedparser.
Unlike NewsData/Twitter, RSS has no search API — feeds are curated per source.
The `query` parameter to `fetch()` is accepted for interface compliance but ignored.

Per-feed rate limiting: one RedisRateLimiter per feed hostname, keyed as
  {source_id}:rss:{hostname}
so a single noisy host cannot exhaust quota for other hosts on the same source.

Malformed/unreachable feeds are logged and skipped — never crash the full pull.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser  # type: ignore[import-untyped]
import structlog

from app.domain.entities import QuotaStatus, RawArticle
from app.infrastructure.connectors.base import RedisRateLimiter

logger = structlog.get_logger(__name__)

_DEFAULT_CALLS_PER_MINUTE = 30


def _host_source_id(source_id: str, url: str) -> str:
    """Return a per-host limiter key derived from source_id + feed hostname."""
    hostname = urlparse(url).netloc or hashlib.sha1(url.encode()).hexdigest()[:12]
    return f"{source_id}:rss:{hostname}"


def _parse_entry_date(entry: Any) -> datetime:
    """Extract publish date from a feedparser entry; fall back to now."""
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                t = tuple(val[:6])
                return datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=UTC)
            except (ValueError, TypeError, IndexError):
                pass
    return datetime.now(UTC)


def _entry_to_article(entry: Any, feed_url: str, feed_title: str = "") -> RawArticle | None:
    """Map a single feedparser entry to RawArticle; return None if required fields absent."""
    link: str | None = getattr(entry, "link", None) or getattr(entry, "id", None)
    title: str | None = getattr(entry, "title", None)
    if not link or not title:
        return None

    # Publisher: prefer feed.title, fall back to hostname.
    publisher = feed_title or urlparse(feed_url).netloc or feed_url

    # Body: prefer full content[0].value, then summary.
    raw_content = ""
    content = getattr(entry, "content", None)
    if content and isinstance(content, list) and content:
        raw_content = getattr(content[0], "value", "") or ""
    if not raw_content:
        raw_content = getattr(entry, "summary", "") or ""

    # Hero image: first enclosure that looks like an image.
    hero_image_url: str | None = None
    for enc in getattr(entry, "enclosures", []) or []:
        enc_type: str = getattr(enc, "type", "") or ""
        enc_url: str = getattr(enc, "href", "") or ""
        if enc_type.startswith("image/") and enc_url:
            hero_image_url = enc_url
            break

    # Stable external_id: use entry.id if present, otherwise the link.
    external_id: str = str(getattr(entry, "id", None) or link)

    return RawArticle(
        external_id=external_id,
        url=str(link),
        headline=str(title),
        publisher=publisher,
        published_at=_parse_entry_date(entry),
        raw_content=raw_content,
        language="en",
        hero_image_url=hero_image_url,
        metadata_json={"feed_url": feed_url},
    )


class RssConnector:
    """Concrete SourceConnector for RSS/Atom feeds.

    Feed URLs are read from source.config_json["feed_urls"] at construction time.
    Each feed hostname gets its own Redis rate-limit bucket so one slow/noisy host
    cannot starve the others.

    The `query` argument to `fetch()` is ignored — RSS feeds are pre-curated.
    The `since` argument filters out entries older than the given datetime.
    """

    source_type = "rss"

    def __init__(
        self,
        source_id: str,
        feed_urls: list[str],
        redis: Any,
        *,
        calls_per_minute: int = _DEFAULT_CALLS_PER_MINUTE,
        failure_threshold: int = 5,
        reset_seconds: int = 120,
    ) -> None:
        self._source_id = source_id
        self._feed_urls = feed_urls
        self._redis = redis
        self._calls_per_minute = calls_per_minute
        self._failure_threshold = failure_threshold
        self._reset_seconds = reset_seconds
        # One limiter per hostname, lazily created.
        self._limiters: dict[str, RedisRateLimiter] = {}

    def _limiter_for(self, url: str) -> RedisRateLimiter:
        host_id = _host_source_id(self._source_id, url)
        if host_id not in self._limiters:
            self._limiters[host_id] = RedisRateLimiter(
                self._redis,
                host_id,
                self._calls_per_minute,
                failure_threshold=self._failure_threshold,
                reset_seconds=self._reset_seconds,
            )
        return self._limiters[host_id]

    async def fetch(self, query: str, since: datetime) -> list[RawArticle]:
        """Fetch all configured feeds; return articles published after `since`.

        `query` is accepted for interface compliance but not used.
        Malformed or unreachable feeds are logged and skipped.
        """
        results: list[RawArticle] = []
        for url in self._feed_urls:
            articles = await self._fetch_one(url, since)
            results.extend(articles)
        return results

    async def remaining_quota(self) -> QuotaStatus:
        """Return aggregate quota status for the first feed hostname (representative)."""
        if not self._feed_urls:
            now = datetime.now(UTC)
            return QuotaStatus(
                source_id=self._source_id,
                calls_made=0,
                quota_limit=self._calls_per_minute,
                window_start=now.replace(second=0, microsecond=0),
            )
        limiter = self._limiter_for(self._feed_urls[0])
        calls = await limiter.calls_this_window()
        open_until = await limiter.circuit_open_until()
        now = datetime.now(UTC)
        return QuotaStatus(
            source_id=self._source_id,
            calls_made=calls,
            quota_limit=self._calls_per_minute,
            window_start=now.replace(second=0, microsecond=0),
            circuit_open=open_until is not None,
            circuit_open_until=open_until,
        )

    async def _fetch_one(self, url: str, since: datetime) -> list[RawArticle]:
        """Fetch and parse a single feed URL; return [] on any error."""
        limiter = self._limiter_for(url)
        try:
            await limiter.acquire()
        except Exception as exc:
            logger.warning(
                "connector.rss.rate_limited",
                source_id=self._source_id,
                feed_url=url,
                reason=str(exc),
            )
            return []

        try:
            # feedparser.parse is synchronous; it handles network + XML parsing.
            parsed = feedparser.parse(url)
        except Exception as exc:
            await limiter.record_failure()
            logger.warning(
                "connector.rss.parse_error",
                source_id=self._source_id,
                feed_url=url,
                error=str(exc),
            )
            return []

        # feedparser sets bozo=True for malformed XML but still returns partial data.
        if parsed.get("bozo"):
            bozo_exc = parsed.get("bozo_exception")
            logger.warning(
                "connector.rss.malformed_feed",
                source_id=self._source_id,
                feed_url=url,
                bozo_exception=str(bozo_exc),
            )
            # Proceed with whatever entries were parsed (best-effort).

        # Propagate feed title as publisher for all entries.
        feed_title: str = getattr(parsed.feed, "title", None) or urlparse(url).netloc

        articles: list[RawArticle] = []
        for entry in parsed.get("entries") or []:
            try:
                article = _entry_to_article(entry, url, feed_title)
            except Exception as exc:
                logger.warning(
                    "connector.rss.entry_error",
                    source_id=self._source_id,
                    feed_url=url,
                    error=str(exc),
                )
                continue
            if article is None:
                continue
            if article.published_at >= since:
                articles.append(article)

        await limiter.record_success()
        logger.info(
            "connector.rss.fetched",
            source_id=self._source_id,
            feed_url=url,
            total=len(parsed.get("entries") or []),
            mapped=len(articles),
        )
        return articles
