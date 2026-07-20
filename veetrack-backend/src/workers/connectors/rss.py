"""RSS/Atom HTTP client for the workers package.

Mirrors apps/api/app/infrastructure/connectors/rss_connector.py in behaviour.
feedparser handles both RSS and Atom; malformed feeds are logged and skipped.

Feed URLs come from source.config_json["feed_urls"].
Per-feed-host rate limiting via RedisRateLimiter (one limiter per hostname).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import structlog

from workers.connectors.base import RedisRateLimiter

logger = structlog.get_logger(__name__)

_DEFAULT_CALLS_PER_MINUTE = 30


@dataclass
class RawArticle:
    external_id: str
    url: str
    headline: str
    publisher: str
    published_at: datetime
    raw_content: str
    language: str = "en"
    hero_image_url: str | None = None
    metadata_json: dict[str, object] = field(default_factory=dict)


def _host_source_id(source_id: str, url: str) -> str:
    hostname = urlparse(url).netloc or hashlib.sha1(url.encode()).hexdigest()[:12]
    return f"{source_id}:rss:{hostname}"


def _parse_entry_date(entry: Any) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                return datetime(*val[:6], tzinfo=UTC)
            except (ValueError, TypeError):
                pass
    return datetime.now(UTC)


def _entry_to_article(entry: Any, feed_url: str, feed_title: str) -> RawArticle | None:
    link: str | None = getattr(entry, "link", None) or getattr(entry, "id", None)
    title: str | None = getattr(entry, "title", None)
    if not link or not title:
        return None

    publisher = feed_title or urlparse(feed_url).netloc or feed_url

    raw_content = ""
    content = getattr(entry, "content", None)
    if content and isinstance(content, list) and content:
        raw_content = getattr(content[0], "value", "") or ""
    if not raw_content:
        raw_content = getattr(entry, "summary", "") or ""

    hero_image_url: str | None = None
    for enc in getattr(entry, "enclosures", []) or []:
        enc_type: str = getattr(enc, "type", "") or ""
        enc_url: str = getattr(enc, "href", "") or ""
        if enc_type.startswith("image/") and enc_url:
            hero_image_url = enc_url
            break

    external_id = str(getattr(entry, "id", None) or link)

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


class RssClient:
    """Async-compatible RSS/Atom client for the workers package.

    feedparser.parse() is synchronous but fast enough for Celery tasks.
    One Redis rate-limit bucket per feed hostname.
    Malformed/unreachable feeds are logged and skipped — never raise.
    """

    def __init__(
        self,
        source_id: str,
        feed_urls: list[str],
        redis: Any,
        *,
        calls_per_minute: int = _DEFAULT_CALLS_PER_MINUTE,
    ) -> None:
        self._source_id = source_id
        self._feed_urls = feed_urls
        self._redis = redis
        self._calls_per_minute = calls_per_minute
        self._limiters: dict[str, RedisRateLimiter] = {}

    def _limiter_for(self, url: str) -> RedisRateLimiter:
        host_id = _host_source_id(self._source_id, url)
        if host_id not in self._limiters:
            self._limiters[host_id] = RedisRateLimiter(
                self._redis, host_id, self._calls_per_minute
            )
        return self._limiters[host_id]

    async def fetch(self, since: datetime) -> list[RawArticle]:
        """Fetch all configured feeds; return articles published after `since`."""
        results: list[RawArticle] = []
        for url in self._feed_urls:
            articles = await self._fetch_one(url, since)
            results.extend(articles)
        return results

    async def _fetch_one(self, url: str, since: datetime) -> list[RawArticle]:
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

        if parsed.get("bozo"):
            logger.warning(
                "connector.rss.malformed_feed",
                source_id=self._source_id,
                feed_url=url,
                bozo_exception=str(parsed.get("bozo_exception")),
            )

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
            if article is not None and article.published_at >= since:
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
