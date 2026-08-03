"""Watchlists router — Phase 24.

CRUD:
  POST   /watchlists            — create watchlist entry
  GET    /watchlists            — list caller's watchlists
  DELETE /watchlists/{id}       — remove a watchlist entry

WebSocket:
  WS     /ws/alerts             — real-time alert stream for the workspace
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.watchlists.create_watchlist import (
    CreateWatchlist,
    CreateWatchlistInput,
)
from app.application.use_cases.watchlists.delete_watchlist import DeleteWatchlist
from app.application.use_cases.watchlists.list_watchlists import ListWatchlists
from app.core.container import get_db_session
from app.core.security_deps import get_current_user, require_role
from app.domain.entities import User
from app.domain.entities.watchlist import Watchlist
from app.domain.value_objects.role import Role
from app.infrastructure.db.repositories.watchlist import SqlAlchemyWatchlistRepository

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["watchlists"])

_VALID_FEEDBACK = frozenset({"useful", "not_useful"})

# ---------------------------------------------------------------------------
# In-process alert broadcast registry (replaced by pub-sub in Phase 25+)
# ---------------------------------------------------------------------------

# workspace_id → set of open WebSocket connections
_connections: dict[str, set[WebSocket]] = {}


def register_connection(workspace_id: str, ws: WebSocket) -> None:
    _connections.setdefault(workspace_id, set()).add(ws)


def unregister_connection(workspace_id: str, ws: WebSocket) -> None:
    conns = _connections.get(workspace_id)
    if conns:
        conns.discard(ws)


async def broadcast_alert(workspace_id: str, payload: dict[str, Any]) -> None:
    """Broadcast an alert payload to all open WebSocket connections in a workspace."""
    conns = list(_connections.get(workspace_id, set()))
    if not conns:
        return
    message = json.dumps(payload)
    results = await asyncio.gather(
        *(ws.send_text(message) for ws in conns),
        return_exceptions=True,
    )
    for ws, exc in zip(conns, results, strict=True):
        if isinstance(exc, Exception):
            logger.warning("ws.send_failed", error=str(exc))
            unregister_connection(workspace_id, ws)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AlertFeedbackRequest(BaseModel):
    feedback: str  # "useful" | "not_useful"


class AlertFeedbackResponse(BaseModel):
    alert_id: str
    user_feedback: str


class WatchlistCreateRequest(BaseModel):
    entity_id: str
    alert_channels: dict[str, bool] = {"websocket": True}


class WatchlistResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    entity_id: str
    alert_channels: dict[str, Any]

    @classmethod
    def from_domain(cls, w: Watchlist) -> WatchlistResponse:
        return cls(
            id=w.id,
            workspace_id=w.workspace_id,
            user_id=w.user_id,
            entity_id=w.entity_id,
            alert_channels=w.alert_channels,
        )


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("/watchlists", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(
    body: WatchlistCreateRequest,
    current_user: Annotated[User, Depends(require_role(Role.analyst))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WatchlistResponse:
    """Watch an entity; analyst role or higher required."""
    repo = SqlAlchemyWatchlistRepository(session)
    use_case = CreateWatchlist(repo)
    result = await use_case.execute(
        CreateWatchlistInput(
            workspace_id=current_user.workspace_id,
            user_id=current_user.id,
            entity_id=body.entity_id,
            alert_channels=body.alert_channels,
        )
    )
    return WatchlistResponse.from_domain(result)


@router.get("/watchlists", response_model=list[WatchlistResponse])
async def list_watchlists(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WatchlistResponse]:
    """List the caller's watchlists."""
    repo = SqlAlchemyWatchlistRepository(session)
    use_case = ListWatchlists(repo)
    items = await use_case.execute(current_user.workspace_id, current_user.id)
    return [WatchlistResponse.from_domain(w) for w in items]


@router.delete("/watchlists/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Delete a watchlist entry owned by the calling user."""
    repo = SqlAlchemyWatchlistRepository(session)
    use_case = DeleteWatchlist(repo)
    await use_case.execute(watchlist_id, current_user.id)


# ---------------------------------------------------------------------------
# Alert feedback endpoint
# ---------------------------------------------------------------------------


@router.post("/alerts/{alert_id}/feedback", response_model=AlertFeedbackResponse)
async def record_alert_feedback(
    alert_id: str,
    body: AlertFeedbackRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AlertFeedbackResponse:
    """Mark an alert as useful or not_useful.

    Any authenticated workspace member can submit feedback on an alert.
    """
    if body.feedback not in _VALID_FEEDBACK:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"feedback must be one of {sorted(_VALID_FEEDBACK)}",
        )
    repo = SqlAlchemyWatchlistRepository(session)
    alert = await repo.record_alert_feedback(
        alert_id=alert_id,
        user_id=current_user.id,
        feedback=body.feedback,
    )
    return AlertFeedbackResponse(
        alert_id=alert.id,
        user_feedback=alert.user_feedback or "",
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/alerts")
async def alerts_websocket(
    ws: WebSocket,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Real-time alert WebSocket.

    The client sends a Bearer token as the first text message (query params
    are insecure for tokens). If the token is missing or invalid the connection
    is closed immediately.
    """
    from app.core.container import get_jwt_service
    from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository

    await ws.accept()

    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
    except (TimeoutError, WebSocketDisconnect):
        await ws.close(code=1008)
        return

    jwt_service = get_jwt_service()
    try:
        payload = jwt_service.decode_access_token(raw.strip())
        user = await SqlAlchemyUserRepository(session).get_by_id(payload["sub"])
    except Exception:
        await ws.close(code=1008)
        return

    workspace_id = user.workspace_id
    register_connection(workspace_id, ws)
    logger.info("ws.connected", user_id=user.id, workspace_id=workspace_id)

    try:
        await ws.send_text(json.dumps({"type": "connected", "workspace_id": workspace_id}))
        while True:
            await asyncio.wait_for(ws.receive_text(), timeout=30.0)
    except (TimeoutError, WebSocketDisconnect):
        pass
    finally:
        unregister_connection(workspace_id, ws)
        logger.info("ws.disconnected", user_id=user.id, workspace_id=workspace_id)
