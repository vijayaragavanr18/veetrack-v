"""Watchlist and Alert domain entities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Watchlist:
    """A user's watch on a specific entity within their workspace."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = ""
    user_id: str = ""
    entity_id: str = ""
    # {"websocket": true, "email": false} etc.
    alert_channels: dict[str, Any] = field(default_factory=lambda: {"websocket": True})


@dataclass
class AlertRecord:
    """A persisted record of an alert that was sent."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    watchlist_id: str = ""
    story_id: str = ""
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    channel: str = "websocket"
    status: str = "pending"
    # Phase 24 revised — decision provenance
    agent_path: str = "fast_path"  # "fast_path" | "agentic" | "fallback"
    reasoning_trace: list[Any] = field(default_factory=list)
    user_feedback: str | None = None  # "useful" | "not_useful" | None
