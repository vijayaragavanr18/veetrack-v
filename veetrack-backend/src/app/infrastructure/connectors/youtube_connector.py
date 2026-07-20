"""YouTube source connector — fully free, no API key required.

Two-step fetch:
  1. Search for videos matching a keyword via yt-dlp (ytsearchN: pseudo-URL).
     yt-dlp scrapes YouTube search results directly — no YouTube Data API key
     or quota needed.
  2. Fetch the English transcript for each video via youtube-transcript-api.
     Also keyless — parses the captions from the video page.

Videos with transcripts disabled / unavailable are logged and skipped without
failing the entire batch.

Rate limiting: yt-dlp search is a network call; we use the same Redis rate
limiter as other connectors.  Default: conservative 5 calls/min to avoid
triggering YouTube's bot-detection throttling.

The full transcript text goes into raw_content.  clean_content is produced by
Phase 11.  Language + is-generated flag go in metadata_json.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

try:
    import yt_dlp  # type: ignore[import-untyped]
except ImportError as _exc:  # pragma: no cover
    raise ImportError("yt-dlp is required for YouTubeConnector") from _exc

try:
    from youtube_transcript_api import (
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        YouTubeTranscriptApi,
    )
except ImportError as _exc:  # pragma: no cover
    raise ImportError("youtube-transcript-api is required for YouTubeConnector") from _exc

from app.domain.entities import QuotaStatus, RawArticle
from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.connectors.base import RedisRateLimiter

logger = structlog.get_logger(__name__)

_PUBLISHER = "YouTube"
_DEFAULT_CALLS_PER_MINUTE = 5
_DEFAULT_MAX_RESULTS = 10

# yt-dlp quiet options — no stdout noise in production
_YDL_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,  # metadata only, don't download video
    "skip_download": True,
}


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _stable_external_id(video_id: str) -> str:
    return f"yt:{video_id}"


def _parse_upload_date(raw: str | None) -> datetime:
    """Parse yt-dlp's upload_date string 'YYYYMMDD' to UTC datetime."""
    if not raw:
        return datetime.now(UTC)
    try:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _build_transcript_text(snippets: list[Any]) -> str:
    """Join transcript snippet texts into a single string."""
    return " ".join(s.text.strip() for s in snippets if s.text.strip())


def map_video_to_article(
    video_id: str,
    info: dict[str, Any],
    transcript_text: str,
    language: str,
    is_generated: bool,
) -> RawArticle:
    """Map a yt-dlp info dict + transcript to RawArticle."""
    title: str = str(info.get("title") or f"YouTube video {video_id}")
    channel: str = str(info.get("channel") or info.get("uploader") or _PUBLISHER)
    published_at = _parse_upload_date(info.get("upload_date"))
    # Thumbnail: yt-dlp puts thumbnails as a list or a single string
    thumbnail: str | None = None
    thumbs = info.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        thumbnail = str(thumbs[-1].get("url", "")) or None
    elif isinstance(info.get("thumbnail"), str):
        thumbnail = info.get("thumbnail")
    description: str = str(info.get("description") or "")
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
            "description": description,
            "is_generated_transcript": is_generated,
            "transcript_language": language,
        },
    )


def _search_videos(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run yt-dlp search synchronously; return list of video info dicts."""
    search_url = f"ytsearch{max_results}:{query}"
    opts = {
        **_YDL_BASE_OPTS,
        "playlistend": max_results,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(search_url, download=False)
    if result is None:
        return []
    entries: list[dict[str, Any]] = result.get("entries") or []
    return [e for e in entries if e and e.get("id")]


class YouTubeConnector:
    """Concrete SourceConnector for YouTube — no API key required.

    Uses yt-dlp for video discovery (scrapes YouTube search) and
    youtube-transcript-api for transcript retrieval (parses captions).
    Rate limiting and circuit breaking via RedisRateLimiter.

    Constructor accepts optional overrides for the search function and
    transcript API instance (used in tests to avoid real network calls).
    """

    source_type = "youtube"

    def __init__(
        self,
        source_id: str,
        rate_limiter: RedisRateLimiter,
        *,
        transcript_api: YouTubeTranscriptApi | None = None,
        search_fn: Any | None = None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        self._source_id = source_id
        self._limiter = rate_limiter
        self._transcript_api = transcript_api or YouTubeTranscriptApi()
        # Allow injection for tests; default to real yt-dlp search
        self._search_fn = search_fn or _search_videos
        self._max_results = max_results

    async def fetch(self, query: str, since: datetime) -> list[RawArticle]:
        """Search YouTube for *query*, fetch transcripts, return RawArticles."""
        await self._limiter.acquire()
        try:
            articles = self._do_fetch(query, since)
            await self._limiter.record_success()
            return articles
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            await self._limiter.record_failure()
            logger.warning(
                "connector.youtube.fetch_failed",
                source_id=self._source_id,
                query=query,
                error=str(exc),
            )
            raise ServiceUnavailableError(f"YouTube fetch failed: {exc}") from exc

    async def remaining_quota(self) -> QuotaStatus:
        calls = await self._limiter.calls_this_window()
        open_until = await self._limiter.circuit_open_until()
        now = datetime.now(UTC)
        return QuotaStatus(
            source_id=self._source_id,
            calls_made=calls,
            quota_limit=_DEFAULT_CALLS_PER_MINUTE,
            window_start=now.replace(second=0, microsecond=0),
            circuit_open=open_until is not None,
            circuit_open_until=open_until,
        )

    def _do_fetch(self, query: str, since: datetime) -> list[RawArticle]:
        try:
            videos = self._search_fn(query, self._max_results)
        except Exception as exc:
            # Re-raise as RuntimeError so the outer fetch() records failure and
            # then wraps it in ServiceUnavailableError (not caught by the
            # `except ServiceUnavailableError: raise` guard).
            raise RuntimeError(f"yt-dlp search failed: {exc}") from exc

        articles: list[RawArticle] = []
        skipped = 0

        for info in videos:
            video_id: str = info["id"]
            # Filter by upload date if available
            upload_date = _parse_upload_date(info.get("upload_date"))
            if upload_date < since:
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

    def _fetch_transcript(
        self, video_id: str, info: dict[str, Any]
    ) -> RawArticle | None:
        """Fetch transcript for one video; return None if unavailable."""
        try:
            fetched = self._transcript_api.fetch(video_id, languages=["en", "en-US"])
            transcript_text = _build_transcript_text(fetched.snippets)
            if not transcript_text.strip():
                logger.info(
                    "connector.youtube.empty_transcript",
                    source_id=self._source_id,
                    video_id=video_id,
                )
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
