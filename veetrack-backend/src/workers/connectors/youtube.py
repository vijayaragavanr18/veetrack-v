"""YouTube client — powered by APIDIRECT MCP (search_youtube tool).

APIDIRECT is an MCP server: POST https://apidirect.io/mcp?token=<key>
with JSON-RPC 2.0. The search_youtube tool returns video metadata
including title, snippet, thumbnail, channel, date, views.

Falls back to yt-dlp + youtube-transcript-api if APIDIRECT key is missing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter

logger = structlog.get_logger(__name__)

_PUBLISHER = "YouTube"
_DEFAULT_CALLS_PER_MINUTE = 10
_DEFAULT_MAX_RESULTS = 10
_APIDIRECT_MCP_URL = "https://apidirect.io/mcp"


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


def _parse_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d"):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


async def _search_apidirect(query: str, max_results: int, api_key: str) -> list[dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_youtube",
            "arguments": {"query": query, "max_results": max_results},
        },
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{_APIDIRECT_MCP_URL}?token={api_key}",
            json=payload,
        )
        resp.raise_for_status()
    data = resp.json()
    import json as _json
    text = data.get("result", {}).get("content", [{}])[0].get("text", "{}")
    parsed = _json.loads(text)
    return parsed.get("posts", parsed.get("videos", []))


def _map_post(post: dict[str, Any]) -> RawArticle:
    video_id = post.get("video_id") or post.get("url", "").split("v=")[-1]
    url = post.get("url") or f"https://youtube.com/watch?v={video_id}"
    return RawArticle(
        external_id=f"yt:{video_id}",
        url=url,
        headline=str(post.get("title") or ""),
        publisher=str(post.get("author") or _PUBLISHER),
        published_at=_parse_date(post.get("date")),
        raw_content=str(post.get("snippet") or ""),
        language="en",
        hero_image_url=post.get("thumbnail"),
        metadata_json={
            "video_id": video_id,
            "channel": post.get("author", ""),
            "views": post.get("views", 0),
            "video_length": post.get("video_length", ""),
            "type": post.get("type", "NORMAL"),
        },
    )


class YouTubeClient:
    """Async YouTube client for Celery workers — uses APIDIRECT MCP."""

    def __init__(
        self,
        source_id: str,
        rate_limiter: RedisRateLimiter,
        *,
        api_key: str = "",
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        self._source_id = source_id
        self._limiter = rate_limiter
        self._api_key = api_key
        self._max_results = max_results

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
                "connector.youtube.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise

    async def _do_fetch(self, query: str, since: datetime) -> list[RawArticle]:
        if self._api_key:
            posts = await _search_apidirect(query, self._max_results, self._api_key)
        else:
            posts = await self._ytdlp_fallback(query)

        articles: list[RawArticle] = []
        for post in posts:
            article = _map_post(post)
            if article.published_at < since:
                continue
            if not article.headline:
                continue
            articles.append(article)

        logger.info(
            "connector.youtube.fetched",
            source_id=self._source_id,
            query=query,
            total=len(posts),
            mapped=len(articles),
        )
        return articles

    async def _ytdlp_fallback(self, query: str) -> list[dict[str, Any]]:
        """Fallback to yt-dlp when no APIDIRECT key."""
        try:
            import yt_dlp  # type: ignore[import-untyped]
        except ImportError:
            return []

        def _search() -> list[dict[str, Any]]:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(f"ytsearch{self._max_results}:{query}", download=False)
            if not result:
                return []
            return [
                {
                    "video_id": e["id"],
                    "url": f"https://www.youtube.com/watch?v={e['id']}",
                    "title": e.get("title", ""),
                    "author": e.get("channel") or e.get("uploader", ""),
                    "date": e.get("upload_date", ""),
                    "snippet": e.get("description", ""),
                    "thumbnail": (e.get("thumbnails") or [{}])[-1].get("url"),
                }
                for e in (result.get("entries") or []) if e and e.get("id")
            ]

        return await asyncio.get_event_loop().run_in_executor(None, _search)
