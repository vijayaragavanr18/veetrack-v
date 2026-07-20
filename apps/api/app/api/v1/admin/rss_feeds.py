"""Admin router: manage RSS feed URLs for a source.

Feed URLs are stored in sources.config_json["feed_urls"] (list of strings).
All endpoints require Role.admin.

GET    /api/v1/admin/sources/{source_id}/rss-feeds         — list current feed URLs
POST   /api/v1/admin/sources/{source_id}/rss-feeds         — add a feed URL
DELETE /api/v1/admin/sources/{source_id}/rss-feeds/{index} — remove feed URL at index
"""

from __future__ import annotations

from typing import Annotated, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import require_role
from app.domain.value_objects.role import Role
from app.infrastructure.db.repositories.source import SqlAlchemySourceRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/sources/{source_id}/rss-feeds", tags=["admin"])


class RssFeedListResponse(BaseModel):
    source_id: str
    feed_urls: list[str]


class AddFeedRequest(BaseModel):
    url: HttpUrl


class AddFeedResponse(BaseModel):
    source_id: str
    feed_urls: list[str]


@router.get("", response_model=RssFeedListResponse)
async def list_rss_feeds(
    source_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> RssFeedListResponse:
    """Return the current list of RSS feed URLs for a source."""
    repo = SqlAlchemySourceRepository(session)
    source = await repo.get_by_id(source_id)
    feed_urls: list[str] = [
        str(u) for u in cast(list[object], source.config_json.get("feed_urls") or [])
    ]
    return RssFeedListResponse(source_id=source_id, feed_urls=feed_urls)


@router.post("", response_model=AddFeedResponse, status_code=201)
async def add_rss_feed(
    source_id: str,
    body: AddFeedRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> AddFeedResponse:
    """Append a feed URL to the source's config_json["feed_urls"] list."""
    repo = SqlAlchemySourceRepository(session)
    source = await repo.get_by_id(source_id)

    url_str = str(body.url)
    feed_urls: list[str] = [
        str(u) for u in cast(list[object], source.config_json.get("feed_urls") or [])
    ]
    if url_str in feed_urls:
        raise HTTPException(status_code=409, detail="Feed URL already exists for this source.")

    feed_urls.append(url_str)
    source.config_json = {**source.config_json, "feed_urls": feed_urls}
    saved = await repo.save(source)

    final_urls: list[str] = [
        str(u) for u in cast(list[object], saved.config_json.get("feed_urls") or [])
    ]
    logger.info("admin.rss_feed_added", source_id=source_id, url=url_str)
    return AddFeedResponse(source_id=source_id, feed_urls=final_urls)


@router.delete("/{feed_index}", status_code=204)
async def remove_rss_feed(
    source_id: str,
    feed_index: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_role(Role.admin))],
) -> None:
    """Remove the feed URL at position `feed_index` from the source's list."""
    repo = SqlAlchemySourceRepository(session)
    source = await repo.get_by_id(source_id)

    feed_urls: list[str] = [
        str(u) for u in cast(list[object], source.config_json.get("feed_urls") or [])
    ]
    if feed_index < 0 or feed_index >= len(feed_urls):
        raise HTTPException(
            status_code=404,
            detail=f"No feed URL at index {feed_index}. Source has {len(feed_urls)} feed(s).",
        )

    removed = feed_urls.pop(feed_index)
    source.config_json = {**source.config_json, "feed_urls": feed_urls}
    await repo.save(source)

    logger.info("admin.rss_feed_removed", source_id=source_id, url=removed, index=feed_index)
