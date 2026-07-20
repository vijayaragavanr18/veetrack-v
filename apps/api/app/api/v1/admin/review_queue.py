"""Admin router — recommendation review queue.

GET  /admin/recommendations/pending-review
  List all recommendations flagged needs_human_review=True. Admin/owner only.

POST /admin/recommendations/{rec_id}/approve
POST /admin/recommendations/{rec_id}/reject
  Approve or reject a flagged recommendation. Both write to audit_log.
  - Approve: sets needs_human_review=False so it appears in the public feed.
  - Reject:  deletes the recommendation row (it will not appear anywhere).
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import get_db_session
from app.core.security_deps import require_role
from app.domain.entities import User
from app.domain.value_objects.role import Role

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/recommendations", tags=["admin"])

_SYSTEM_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"


class PendingRecommendationResponse(BaseModel):
    id: str
    story_id: str
    audience: str
    recommendation_text: str
    risk_level: str
    confidence_score: float
    generated_at: str


class ReviewActionResponse(BaseModel):
    id: str
    action: str
    audit_log_id: str


@router.get("/pending-review", response_model=list[PendingRecommendationResponse])
async def list_pending_review(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    reviewer: Annotated[User, Depends(require_role(Role.admin))],
) -> list[PendingRecommendationResponse]:
    """Return all recommendations awaiting human review, newest first."""
    rows = await session.execute(
        text(
            "SELECT id, story_id, audience, recommendation_text, "
            "       risk_level, confidence_score, generated_at "
            "FROM story_recommendations "
            "WHERE needs_human_review = true "
            "ORDER BY generated_at DESC"
        )
    )
    return [
        PendingRecommendationResponse(
            id=str(r.id),
            story_id=str(r.story_id),
            audience=str(r.audience),
            recommendation_text=str(r.recommendation_text),
            risk_level=str(r.risk_level),
            confidence_score=float(r.confidence_score),
            generated_at=r.generated_at.isoformat() if r.generated_at else "",
        )
        for r in rows
    ]


@router.post("/{rec_id}/approve", response_model=ReviewActionResponse)
async def approve_recommendation(
    rec_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    reviewer: Annotated[User, Depends(require_role(Role.admin))],
) -> ReviewActionResponse:
    """Approve a pending recommendation: clears needs_human_review and logs to audit_log."""
    result = await session.execute(
        text(
            "UPDATE story_recommendations "
            "SET needs_human_review = false "
            "WHERE id = :id AND needs_human_review = true "
            "RETURNING id, story_id"
        ),
        {"id": rec_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found or already reviewed",
        )

    audit_id = await _write_audit(
        session,
        action="recommendation.approved",
        resource_type="story_recommendation",
        resource_id=rec_id,
        user_id=reviewer.id,
        workspace_id=reviewer.workspace_id,
    )

    logger.info("review_queue.approved", rec_id=rec_id, reviewer=reviewer.id)
    return ReviewActionResponse(id=rec_id, action="approved", audit_log_id=audit_id)


@router.post("/{rec_id}/reject", response_model=ReviewActionResponse)
async def reject_recommendation(
    rec_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    reviewer: Annotated[User, Depends(require_role(Role.admin))],
) -> ReviewActionResponse:
    """Reject and delete a pending recommendation; logs to audit_log."""
    result = await session.execute(
        text(
            "DELETE FROM story_recommendations "
            "WHERE id = :id AND needs_human_review = true "
            "RETURNING id"
        ),
        {"id": rec_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Recommendation not found or already reviewed",
        )

    audit_id = await _write_audit(
        session,
        action="recommendation.rejected",
        resource_type="story_recommendation",
        resource_id=rec_id,
        user_id=reviewer.id,
        workspace_id=reviewer.workspace_id,
    )

    logger.info("review_queue.rejected", rec_id=rec_id, reviewer=reviewer.id)
    return ReviewActionResponse(id=rec_id, action="rejected", audit_log_id=audit_id)


async def _write_audit(
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: str,
    workspace_id: str,
) -> str:
    audit_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, plan) "
            "VALUES (:id, 'system', 'system') ON CONFLICT DO NOTHING"
        ),
        {"id": _SYSTEM_WORKSPACE_ID},
    )
    await session.execute(
        text(
            "INSERT INTO audit_log (id, workspace_id, user_id, action, resource_type, resource_id) "
            "VALUES (:id, :wid, :uid, :action, :rtype, :rid)"
        ),
        {
            "id": audit_id,
            "wid": workspace_id,
            "uid": user_id,
            "action": action,
            "rtype": resource_type,
            "rid": resource_id,
        },
    )
    return audit_id
