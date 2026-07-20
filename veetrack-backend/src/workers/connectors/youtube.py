"""YouTube client for the workers package — fully free, no API key required.

Uses yt-dlp for video search (scrapes YouTube) and youtube-transcript-api
for transcript retrieval.  Both are keyless and unlimited.

Rate limiting: conservative default of 5 calls/minute via RedisRateLimiter
to avoid YouTube's bot-detection throttling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from workers.connectors.base import CircuitOpen, RateLimitExceeded, RedisRateLimiter

try:
    import yt_dlp  # type: ignore[import-untyped]
except ImportError as _exc:
    raise ImportError("yt-dlp required for YouTubeClient") from _exc

try:
    from youtube_transcript_api import (  # type: ignore[import-untyped]
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )
except ImportError as _exc:
    raise ImportError("youtube-transcript-api required for YouTubeClient") from _exc

logger = structlog.get_logger(__name__)

_PUBLISHER = "YouTube"
_DEFAULT_CALLS_PER_MINUTE = 5
_DEFAULT_MAX_RESULTS = 10

_YDL_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "skip_download": True,
}


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


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _stable_external_id(video_id: str) -> str:
    return f"yt:{video_id}"


def _parse_upload_date(raw: str | None) -> datetime:
    """Parse yt-dlp's upload_date 'YYYYMMDD' to UTC datetime."""
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _build_transcript_text(snippets: list[Any]) -> str:
    return " ".join(s.text.strip() for s in snippets if s.text.strip())


def map_video_to_article(
    video_id: str,
    info: dict[str, Any],
    transcript_text: str,
    language: str,
    is_generated: bool,
) -> RawArticle:
    title = str(info.get("title") or f"YouTube video {video_id}")
    channel = str(info.get("channel") or info.get("uploader") or _PUBLISHER)
    published_at = _parse_upload_date(info.get("upload_date"))
    thumbnail: str | None = None
    thumbs = info.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        thumbnail = str(thumbs[-1].get("url", "")) or None
    elif isinstance(info.get("thumbnail"), str):
        thumbnail = info.get("thumbnail")
    return RawArticle(
        external_id=_stable_external_id(video_id),
        url=_video_url(video_id),
        headline=title,
        publisher=channel,
        published_at=published_at,
        raw_content=transcript_text,
        language=language,
        hero_image_url=thumbnail,
        metadata_json={
            "video_id": video_id,
            "channel": channel,
            "description": str(info.get("description") or ""),
            "is_generated_transcript": is_generated,
            "transcript_language": language,
        },
    )


def _search_videos(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run yt-dlp search synchronously; return video info dicts."""
    search_url = f"ytsearch{max_results}:{query}"
    opts = {**_YDL_BASE_OPTS, "playlistend": max_results}
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(search_url, download=False)
    if result is None:
        return []
    entries: list[dict[str, Any]] = result.get("entries") or []
    return [e for e in entries if e and e.get("id")]


class YouTubeClient:
    """Async-compatible YouTube client for Celery workers — no API key needed."""

    def __init__(
        self,
        source_id: str,
        rate_limiter: RedisRateLimiter,
        *,
        transcript_api: Any | None = None,
        search_fn: Any | None = None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        self._source_id = source_id
        self._limiter = rate_limiter
        self._transcript_api = transcript_api or YouTubeTranscriptApi()
        self._search_fn = search_fn or _search_videos
        self._max_results = max_results

    async def fetch(self, query: str, since: datetime) -> list[RawArticle]:
        await self._limiter.acquire()
        try:
            articles = self._do_fetch(query, since)
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

    def _do_fetch(self, query: str, since: datetime) -> list[RawArticle]:
        try:
            videos = self._search_fn(query, self._max_results)
        except Exception as exc:
            raise RuntimeError(f"yt-dlp search failed: {exc}") from exc

        articles: list[RawArticle] = []
        skipped = 0

        for info in videos:
            video_id: str = info["id"]
            if _parse_upload_date(info.get("upload_date")) < since:
                continue
            article = self._fetch_transcript(video_id, info)
            if article is not None:
                articles.append(article)
            else:
                skipped += 1

        logger.info(
            "connector.youtube.fetched",
            source_id=self._source_id,
            query=query,
            total=len(videos),
            mapped=len(articles),
            skipped_no_transcript=skipped,
        )
        return articles

    def _fetch_transcript(self, video_id: str, info: dict[str, Any]) -> RawArticle | None:
        try:
            fetched = self._transcript_api.fetch(video_id, languages=["en", "en-US"])
            transcript_text = _build_transcript_text(fetched.snippets)
            if not transcript_text.strip():
                return None
            return map_video_to_article(
                video_id=video_id,
                info=info,
                transcript_text=transcript_text,
                language=fetched.language_code,
                is_generated=fetched.is_generated,
            )
        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
            logger.info(
                "connector.youtube.no_transcript",
                source_id=self._source_id,
                video_id=video_id,
            )
            return None
        except CouldNotRetrieveTranscript as exc:
            logger.warning(
                "connector.youtube.transcript_error",
                source_id=self._source_id,
                video_id=video_id,
                error=str(exc),
            )
            return None
        except Exception as exc:
            logger.warning(
                "connector.youtube.transcript_unexpected_error",
                source_id=self._source_id,
                video_id=video_id,
                error=str(exc),
            )
            return None
