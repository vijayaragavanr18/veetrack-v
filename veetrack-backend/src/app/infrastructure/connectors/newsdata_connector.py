"""NewsData.io source connector.

Maps the NewsData.io `/news/search` response to the common RawArticle DTO.
All outbound calls go through RedisRateLimiter — no connector call can bypass it.

API docs: https://newsdata.io/documentation
"""

from __future__ import annotations

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

from app.domain.entities import QuotaStatus, RawArticle
from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.connectors.base import RedisRateLimiter

logger = structlog.get_logger(__name__)

_BASE_URL = "https://newsdata.io/api/1"
_SEARCH_PATH = "/news/search"

# Retry policy: up to 3 attempts with exponential back-off on transient errors.
# Does NOT retry on 4xx (auth/quota errors) — only on network/5xx.

# NewsData.io free tier: 200 requests/day ≈ 0.14/min.  We express the budget
# as calls-per-minute; source.rate_limit_budget * 60 gives us that number.
_DEFAULT_CALLS_PER_MINUTE = 10


def _parse_published_at(raw: str | None) -> datetime:
    """Parse NewsData.io's 'pubDate' field ('YYYY-MM-DD HH:MM:SS') to UTC datetime."""
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _map_article(item: dict[str, Any], source_id: str) -> RawArticle | None:
    """Map a single NewsData.io result dict to RawArticle; return None if invalid."""
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


class NewsDataConnector:
    """Concrete SourceConnector for NewsData.io.

    Each instance is bound to one Source row (identified by source_id).
    The rate limiter is Redis-backed so it is safe under concurrent workers.
    """

    source_type = "newsdata"

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
        """Pull articles for *query* published after *since*.

        Rate-limited and circuit-broken via RedisRateLimiter.
        Uses tenacity retry on transient network errors.
        """
        await self._limiter.acquire()
        try:
            articles: list[RawArticle] = await self._fetch_with_retry(query, since)
            await self._limiter.record_success()
            return articles
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            await self._limiter.record_failure()
            logger.warning(
                "connector.newsdata.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise ServiceUnavailableError(f"NewsData.io fetch failed: {exc}") from exc

    async def remaining_quota(self) -> QuotaStatus:
        calls = await self._limiter.calls_this_window()
        open_until = await self._limiter.circuit_open_until()
        now = datetime.now(UTC)
        minute_start = now.replace(second=0, microsecond=0)
        return QuotaStatus(
            source_id=self._source_id,
            calls_made=calls,
            quota_limit=_DEFAULT_CALLS_PER_MINUTE,
            window_start=minute_start,
            circuit_open=open_until is not None,
            circuit_open_until=open_until,
        )

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_with_retry(self, query: str, since: datetime) -> list[RawArticle]:
        from_date = since.strftime("%Y-%m-%d")
        params: dict[str, str] = {
            "apikey": self._api_key,
            "q": query,
            "from_date": from_date,
            "language": "en",
        }
        resp = await self._http.get(f"{_BASE_URL}{_SEARCH_PATH}", params=params)

        if resp.status_code == 401:
            raise ServiceUnavailableError("NewsData.io: invalid API key (401)")
        if resp.status_code == 429:
            raise ServiceUnavailableError("NewsData.io: quota exhausted (429)")
        if resp.status_code >= 500:
            # 5xx — tenacity will retry
            raise httpx.HTTPStatusError(
                f"NewsData.io server error {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        if data.get("status") != "success":
            raise ServiceUnavailableError(f"NewsData.io: unexpected status {data.get('status')!r}")

        results: list[RawArticle] = []
        for item in data.get("results") or []:
            article = _map_article(item, self._source_id)
            if article is not None:
                results.append(article)

        logger.info(
            "connector.newsdata.fetched",
            source_id=self._source_id,
            query=query,
            count=len(results),
        )
        return results
