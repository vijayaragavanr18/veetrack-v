"""Exports router — Phase 25.

POST /exports/brief
  Synchronous for ≤ 50 stories (small workspace). Returns:
    - Content-Type: application/pdf  when ?format=pdf  (default)
    - Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
                    when ?format=pptx

  Decision: sync for typical PR/exec briefings (≤50 stories, ~1–3 s render).
  An async job pattern would add latency for the common case; document here if
  large workspaces need it in future.
"""

from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.exports.build_brief import BuildBrief, BuildBriefInput
from app.core.container import get_db_session
from app.core.security_deps import get_current_user
from app.domain.entities import User

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["exports"])

ExportFormat = Literal["pdf", "pptx"]

_PDF_MIME = "application/pdf"
_PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


@router.post("/exports/brief")
async def export_brief(
    entity: Annotated[str, Query(min_length=1, max_length=200)],
    format: Annotated[ExportFormat, Query()] = "pdf",
    window_days: Annotated[int, Query(ge=1, le=90)] = 7,
    max_stories: Annotated[int, Query(ge=1, le=50)] = 10,
    session: Annotated[AsyncSession, Depends(get_db_session)] = ...,  # type: ignore[assignment]
    current_user: Annotated[User, Depends(get_current_user)] = ...,  # type: ignore[assignment]
) -> Response:
    """Generate and return an executive brief as PDF or PPTX.

    Sync for ≤50 stories. If response latency becomes an issue for large
    workspaces, wrap in a background job and return 202 + polling URL.
    """
    async def _db_query(sql: str, params: dict) -> list[dict]:
        result = await session.execute(text(sql), params)
        columns = result.keys()
        return [dict(zip(columns, row, strict=True)) for row in result]

    inp = BuildBriefInput(
        workspace_id=current_user.workspace_id,
        entity_keyword=entity,
        window_days=window_days,
        max_stories=max_stories,
    )
    use_case = BuildBrief(db_query=_db_query)
    brief = await use_case.execute(inp)

    logger.info(
        "exports.brief_requested",
        user_id=current_user.id,
        workspace_id=current_user.workspace_id,
        entity=entity,
        format=format,
        stories=len(brief.stories),
    )

    try:
        if format == "pdf":
            from app.infrastructure.exports.pdf_renderer import render_pdf

            payload = await _run_sync(render_pdf, brief)
            filename = f"veetrack_brief_{_slug(entity)}.pdf"
            return Response(
                content=payload,
                media_type=_PDF_MIME,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                },
            )
        else:
            from app.infrastructure.exports.pptx_renderer import render_pptx

            payload = await _run_sync(render_pptx, brief)
            filename = f"veetrack_brief_{_slug(entity)}.pptx"
            return Response(
                content=payload,
                media_type=_PPTX_MIME,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control": "no-store",
                },
            )
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Export renderer unavailable: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_sync(fn, *args):  # type: ignore[no-untyped-def]
    """Run a blocking renderer in a thread pool to avoid blocking the event loop."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:40]
