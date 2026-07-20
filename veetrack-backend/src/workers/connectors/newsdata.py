"""NewsData.io HTTP client for the workers package.

Mirrors apps/api/app/infrastructure/connectors/newsdata_connector.py in behaviour
but is kept separate to avoid cross-package coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter

logger = structlog.get_logger(__name__)

_BASE_URL = "https://newsdata.io/api/1"
_SEARCH_PATH = "/latest"

_RETRY_POLICY = dict(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)


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


def _parse_published_at(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _map_article(item: dict[str, Any]) -> RawArticle | None:
    article_id: str | None = item.get("article_id") or item.get("link")
    url: str | None = item.get("link")
    headline: str | None = item.get("title")
    if not article_id or not url or not headline:
        return None
    return RawArticle(
        external_id=str(article_id),
        url=str(url),
        headline=str(headline),
        publisher=str(item.get("source_name") or item.get("source_id") or ""),
        published_at=_parse_published_at(item.get("pubDate")),
        raw_content=str(item.get("content") or item.get("description") or ""),
        language=str(item.get("language") or "en"),
        hero_image_url=item.get("image_url") or None,
    )


class NewsDataClient:
    """Async HTTP client for NewsData.io, with rate limiting and retry."""

    def __init__(
        self,
        api_key: str,
        source_id: str,
        rate_limiter: RedisRateLimiter,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._source_id = source_id
        self._limiter = rate_limiter
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def fetch(self, query: str, since: datetime) -> list[RawArticle]:
        await self._limiter.acquire()
        try:
            articles = await self._do_fetch(query, since)
            await self._limiter.record_success()
            return articles
        except (CircuitOpen, RateLimitExceeded):
            raise
        except Exception as exc:
            await self._limiter.record_failure()
            logger.warning(
                "connector.newsdata.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise

    @retry(**_RETRY_POLICY)
    async def _do_fetch(self, query: str, since: datetime) -> list[RawArticle]:
        params: dict[str, str] = {
            "apikey": self._api_key,
            "q": query,
            "language": "en",
            "size": "10",
        }
        resp = await self._http.get(f"{_BASE_URL}{_SEARCH_PATH}", params=params)

        if resp.status_code in (401, 403):
            raise RuntimeError(f"NewsData.io: auth error {resp.status_code}")
        if resp.status_code == 429:
            raise RateLimitExceeded("NewsData.io: quota exhausted (429)")
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"NewsData.io server error {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"NewsData.io: unexpected status {data.get('status')!r}")

        results = []
        for item in data.get("results") or []:
            article = _map_article(item)
            if article is not None and article.published_at >= since:
                results.append(article)

        logger.info(
            "connector.newsdata.fetched",
            source_id=self._source_id,
            query=query,
            count=len(results),
        )
        return results
