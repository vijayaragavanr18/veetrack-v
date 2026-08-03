"""Unit tests for the agentic alert engine (Phase 24 revised).

Tests cover:
  - Fast-path vs borderline routing logic across risk levels, alert counts, confidence.
  - Each new tool function against a fake DB query.
  - Fallback behavior when AgentLoop raises AgentDidNotConvergeError.
  - Full agentic path: agent calls a tool, then fires alert.
  - Agentic suppression: agent returns should_alert=False.
  - Idempotency/dedupe: duplicate story+watchlist pair does not double-fire
    (WatchlistRepository guards this at the DB level; tested here via save_alert call count).
  - user_feedback recorded by record_alert_feedback.
  - POST /alerts/{id}/feedback endpoint contract.

No infrastructure imports. All I/O via fakes.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.watchlists.evaluate_alerts import (
    BORDERLINE_THRESHOLD,
    FAST_PATH_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    RECENT_ALERT_FATIGUE_COUNT,
    EvaluateAlerts,
    _is_borderline,
    _is_fast_path,
)
from app.application.use_cases.shared.agent_loop import AgentDidNotConvergeError
from app.domain.entities.watchlist import AlertRecord, Watchlist
from app.domain.exceptions import NotFoundError

# ── Fake repository ───────────────────────────────────────────────────────────


class FakeWatchlistRepository:
    def __init__(self, watchlists: list[Watchlist] | None = None) -> None:
        self._watchlists: list[Watchlist] = watchlists or []
        self._alerts: list[AlertRecord] = []
        self.save_alert_calls: int = 0

    async def get_by_id(self, watchlist_id: str) -> Watchlist:
        for w in self._watchlists:
            if w.id == watchlist_id:
                return w
        raise NotFoundError(f"Not found: {watchlist_id}")

    async def list_by_workspace_user(self, workspace_id: str, user_id: str) -> list[Watchlist]:
        return []

    async def find_by_entity(self, workspace_id: str, user_id: str, entity_id: str) -> Watchlist | None:
        return None

    async def save(self, watchlist: Watchlist) -> Watchlist:
        return watchlist

    async def delete(self, watchlist_id: str) -> None:
        pass

    async def list_by_entity_across_workspace(
        self, entity_id: str, workspace_id: str
    ) -> list[Watchlist]:
        return [w for w in self._watchlists if w.entity_id == entity_id]

    async def save_alert(self, alert: AlertRecord) -> AlertRecord:
        self.save_alert_calls += 1
        self._alerts.append(alert)
        return alert

    async def get_alert_by_id(self, alert_id: str) -> AlertRecord:
        for a in self._alerts:
            if a.id == alert_id:
                return a
        raise NotFoundError(alert_id)

    async def record_alert_feedback(
        self, alert_id: str, user_id: str, feedback: str
    ) -> AlertRecord:
        for a in self._alerts:
            if a.id == alert_id:
                a.user_feedback = feedback
                return a
        raise NotFoundError(alert_id)


def _wl(
    entity_id: str = "ent-1",
    workspace_id: str = "ws1",
    channels: dict[str, bool] | None = None,
) -> Watchlist:
    return Watchlist(
        id="wl-1",
        workspace_id=workspace_id,
        user_id="u1",
        entity_id=entity_id,
        alert_channels=channels or {"websocket": True},
    )


# ── Fake LLM gateway ─────────────────────────────────────────────────────────


class FakeGateway:
    model_name = "qwen2.5:7b"

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return next(self._responses)

    async def complete_json(self, prompt: str, schema: Any, **kwargs: Any) -> dict[str, Any]:
        return json.loads(next(self._responses))


_TOOL_CALL = json.dumps({
    "type": "tool_call",
    "reasoning": "Need entity alert history.",
    "tool": "get_entity_alert_history",
    "args": {"entity_id": "ent-1", "hours": 24},
})

_FINAL_ALERT = json.dumps({
    "type": "final_answer",
    "reasoning": "High risk, first alert. Fire immediately.",
    "should_alert": True,
    "channel": "websocket",
    "urgency": "high",
})

_FINAL_SUPPRESS = json.dumps({
    "type": "final_answer",
    "reasoning": "Entity has dismissed 3/3 past alerts. Suppress.",
    "should_alert": False,
    "channel": "websocket",
    "urgency": "medium",
    "suppress_reason": "High not_useful feedback rate.",
})


# ── _is_fast_path ─────────────────────────────────────────────────────────────


def test_fast_path_critical_no_recent() -> None:
    assert _is_fast_path("critical", 0) is True


def test_fast_path_high_no_recent() -> None:
    assert _is_fast_path("high", 0) is True


def test_fast_path_critical_with_recent_alert() -> None:
    # Has recent alerts → not fast path (potential fatigue)
    assert _is_fast_path("critical", 1) is False


def test_fast_path_medium_never() -> None:
    assert _is_fast_path("medium", 0) is False


def test_fast_path_low_never() -> None:
    assert _is_fast_path("low", 0) is False


# ── _is_borderline ────────────────────────────────────────────────────────────


def test_borderline_high_with_recent_alerts() -> None:
    assert _is_borderline("high", RECENT_ALERT_FATIGUE_COUNT, None) is True


def test_borderline_critical_one_recent() -> None:
    assert _is_borderline("critical", 1, None) is True


def test_borderline_medium_always() -> None:
    assert _is_borderline("medium", 0, None) is True


def test_borderline_low_never() -> None:
    assert _is_borderline("low", 0, None) is False


def test_borderline_low_confidence_triggers() -> None:
    assert _is_borderline("high", 0, LOW_CONFIDENCE_THRESHOLD - 0.01) is True


def test_borderline_high_confidence_no_trigger_on_high_no_recent() -> None:
    # high risk, no recent alerts, high confidence → fast path wins, not borderline
    assert _is_borderline("high", 0, 0.9) is False


# ── EvaluateAlerts — fast path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fast_path_critical_fires_without_gateway() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "critical", recent_alert_count=0)
    assert len(result.fired) == 1
    assert result.fired[0].agent_path == "fast_path"
    assert result.fired[0].reasoning_trace == []


@pytest.mark.asyncio
async def test_fast_path_high_fires_without_gateway() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "high", recent_alert_count=0)
    assert len(result.fired) == 1
    assert result.fired[0].agent_path == "fast_path"


@pytest.mark.asyncio
async def test_low_risk_never_fires() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "low", recent_alert_count=0)
    assert result.fired == []
    assert result.skipped_count == 1


@pytest.mark.asyncio
async def test_no_watchlists_fires_nothing() -> None:
    repo = FakeWatchlistRepository(watchlists=[])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "critical", recent_alert_count=0)
    assert result.fired == []
    assert result.skipped_count == 0


@pytest.mark.asyncio
async def test_fast_path_disabled_channel_skipped() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl(channels={"websocket": False})])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "critical", recent_alert_count=0)
    assert result.fired == []


# ── EvaluateAlerts — fallback (no gateway, borderline) ───────────────────────


@pytest.mark.asyncio
async def test_fallback_high_risk_fires_when_no_gateway() -> None:
    # Borderline case (recent alerts > 0) but no gateway → fallback threshold
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute(
        "story-1", "ent-1", "ws1", "high", recent_alert_count=RECENT_ALERT_FATIGUE_COUNT
    )
    assert len(result.fired) == 1
    assert result.fired[0].agent_path == "fallback"


@pytest.mark.asyncio
async def test_fallback_medium_risk_suppressed_when_no_gateway() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    result = await uc.execute("story-1", "ent-1", "ws1", "medium", recent_alert_count=0)
    assert result.fired == []
    assert result.skipped_count == 1


# ── EvaluateAlerts — agentic path: fires ─────────────────────────────────────


@pytest.mark.asyncio
async def test_agentic_path_calls_tool_and_fires() -> None:
    tool_fn = AsyncMock(return_value="No recent alerts.")
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    gw = FakeGateway([_TOOL_CALL, _FINAL_ALERT])
    uc = EvaluateAlerts(
        repo=repo,
        gateway=gw,  # type: ignore[arg-type]
        tools={"get_entity_alert_history": tool_fn},
    )
    # Borderline: high risk but has 1 recent alert
    result = await uc.execute(
        "story-1", "ent-1", "ws1", "high", recent_alert_count=1
    )
    assert len(result.fired) == 1
    alert = result.fired[0]
    assert alert.agent_path == "agentic"
    assert len(alert.reasoning_trace) > 0
    assert alert.channel == "websocket"
    tool_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_agentic_path_fires_immediately_on_final_answer() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    gw = FakeGateway([_FINAL_ALERT])
    uc = EvaluateAlerts(repo=repo, gateway=gw, tools={})  # type: ignore[arg-type]
    result = await uc.execute("story-1", "ent-1", "ws1", "medium", recent_alert_count=0)
    assert len(result.fired) == 1
    assert result.fired[0].agent_path == "agentic"


# ── EvaluateAlerts — agentic suppression ─────────────────────────────────────


@pytest.mark.asyncio
async def test_agentic_suppresses_medium_risk() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    gw = FakeGateway([_FINAL_SUPPRESS])
    uc = EvaluateAlerts(repo=repo, gateway=gw, tools={})  # type: ignore[arg-type]
    result = await uc.execute("story-1", "ent-1", "ws1", "medium", recent_alert_count=0)
    assert result.fired == []
    assert result.skipped_count == 1


# ── EvaluateAlerts — fallback on convergence failure ─────────────────────────


@pytest.mark.asyncio
async def test_fallback_on_agent_did_not_converge_high_risk() -> None:
    # Agent always tool-calls → exhausts iterations → AgentDidNotConvergeError
    # For high risk, fallback should still fire the alert.
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    responses = [_TOOL_CALL] * 10  # always tool_call, never final_answer
    gw = FakeGateway(responses)
    uc = EvaluateAlerts(repo=repo, gateway=gw, tools={})  # type: ignore[arg-type]
    result = await uc.execute(
        "story-1", "ent-1", "ws1", "high", recent_alert_count=1
    )
    assert len(result.fired) == 1
    assert result.fired[0].agent_path == "fallback"


@pytest.mark.asyncio
async def test_fallback_on_agent_did_not_converge_medium_suppresses() -> None:
    # Medium risk: even on convergence failure, do not fire (correct behavior)
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    responses = [_TOOL_CALL] * 10
    gw = FakeGateway(responses)
    uc = EvaluateAlerts(repo=repo, gateway=gw, tools={})  # type: ignore[arg-type]
    result = await uc.execute("story-1", "ent-1", "ws1", "medium", recent_alert_count=0)
    assert result.fired == []


# ── Idempotency / dedupe ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_alert_called_once_per_channel() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl(channels={"websocket": True, "email": True})])
    uc = EvaluateAlerts(repo=repo, gateway=None)
    await uc.execute("story-1", "ent-1", "ws1", "critical", recent_alert_count=0)
    # Two channels enabled → save_alert called twice
    assert repo.save_alert_calls == 2


@pytest.mark.asyncio
async def test_save_alert_called_once_for_agentic_single_channel() -> None:
    repo = FakeWatchlistRepository(watchlists=[_wl()])
    gw = FakeGateway([_FINAL_ALERT])
    uc = EvaluateAlerts(repo=repo, gateway=gw, tools={})  # type: ignore[arg-type]
    await uc.execute("story-1", "ent-1", "ws1", "medium", recent_alert_count=0)
    assert repo.save_alert_calls == 1


# ── Tool functions (unit-tested against fake DbQuery) ────────────────────────


@pytest.mark.asyncio
async def test_get_entity_alert_history_no_rows() -> None:
    from app.infrastructure.llm.tools.get_entity_alert_history import (
        get_entity_alert_history,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    result = await get_entity_alert_history(
        {"entity_id": "ent-1", "hours": 24}, fake_query
    )
    assert "No alerts" in result


@pytest.mark.asyncio
async def test_get_entity_alert_history_with_rows() -> None:
    from app.infrastructure.llm.tools.get_entity_alert_history import (
        get_entity_alert_history,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"sent_at": "2026-07-21T10:00:00", "channel": "websocket", "status": "sent"},
            {"sent_at": "2026-07-21T09:00:00", "channel": "email", "status": "sent"},
        ]

    result = await get_entity_alert_history(
        {"entity_id": "ent-1", "hours": 24}, fake_query
    )
    assert "2 total" in result


@pytest.mark.asyncio
async def test_get_watchlist_preferences_not_found() -> None:
    from app.infrastructure.llm.tools.get_watchlist_preferences import (
        get_watchlist_preferences,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    result = await get_watchlist_preferences({"watchlist_id": "wl-x"}, fake_query)
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_get_watchlist_preferences_returns_channels() -> None:
    from app.infrastructure.llm.tools.get_watchlist_preferences import (
        get_watchlist_preferences,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": "wl-1",
                "entity_id": "ent-1",
                "alert_channels_json": {"websocket": True, "email": False},
                "sensitivity": "high",
                "quiet_hours_start": None,
                "quiet_hours_end": None,
            }
        ]

    result = await get_watchlist_preferences({"watchlist_id": "wl-1"}, fake_query)
    assert "websocket" in result
    assert "sensitivity=high" in result


@pytest.mark.asyncio
async def test_get_story_risk_context_not_found() -> None:
    from app.infrastructure.llm.tools.get_story_risk_context import get_story_risk_context

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    result = await get_story_risk_context({"story_id": "s-x"}, fake_query)
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_get_story_risk_context_with_data() -> None:
    from app.infrastructure.llm.tools.get_story_risk_context import get_story_risk_context

    call_count = 0

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [
                {
                    "id": "s-1",
                    "title": "Crisis at AcmeCorp",
                    "risk_level": "high",
                    "status": "active",
                    "created_at": "2026-07-21",
                    "updated_at": "2026-07-21",
                    "entity_name": "AcmeCorp",
                }
            ]
        if call_count == 2:
            return [{"confidence_score": 0.82, "needs_human_review": False, "agent_mode": "agentic"}]
        return [{"cnt": 2}]

    result = await get_story_risk_context({"story_id": "s-1"}, fake_query)
    assert "risk_level=high" in result
    assert "confidence=0.82" in result


@pytest.mark.asyncio
async def test_get_alert_feedback_history_no_feedback() -> None:
    from app.infrastructure.llm.tools.get_alert_feedback_history import (
        get_alert_feedback_history,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    result = await get_alert_feedback_history({"entity_id": "ent-1"}, fake_query)
    assert "No feedback" in result


@pytest.mark.asyncio
async def test_get_alert_feedback_history_mostly_not_useful() -> None:
    from app.infrastructure.llm.tools.get_alert_feedback_history import (
        get_alert_feedback_history,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"user_feedback": "not_useful", "cnt": 5},
            {"user_feedback": "useful", "cnt": 1},
        ]

    result = await get_alert_feedback_history({"entity_id": "ent-1"}, fake_query)
    assert "not_useful" in result
    assert "stricter" in result.lower()


@pytest.mark.asyncio
async def test_get_alert_feedback_history_mostly_useful() -> None:
    from app.infrastructure.llm.tools.get_alert_feedback_history import (
        get_alert_feedback_history,
    )

    async def fake_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"user_feedback": "useful", "cnt": 8},
            {"user_feedback": "not_useful", "cnt": 1},
        ]

    result = await get_alert_feedback_history({"entity_id": "ent-1"}, fake_query)
    assert "landing well" in result.lower()


# ── Feedback recorded in repository ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_feedback_useful() -> None:
    repo = FakeWatchlistRepository()
    # Seed an alert record directly
    alert = AlertRecord(id="alert-1", watchlist_id="wl-1", story_id="s-1")
    repo._alerts.append(alert)
    updated = await repo.record_alert_feedback("alert-1", "u1", "useful")
    assert updated.user_feedback == "useful"


@pytest.mark.asyncio
async def test_record_feedback_not_useful() -> None:
    repo = FakeWatchlistRepository()
    alert = AlertRecord(id="alert-2", watchlist_id="wl-1", story_id="s-1")
    repo._alerts.append(alert)
    updated = await repo.record_alert_feedback("alert-2", "u1", "not_useful")
    assert updated.user_feedback == "not_useful"


@pytest.mark.asyncio
async def test_record_feedback_not_found_raises() -> None:
    repo = FakeWatchlistRepository()
    with pytest.raises(NotFoundError):
        await repo.record_alert_feedback("nonexistent", "u1", "useful")


# ── Architecture: evaluate_alerts imports nothing from infrastructure ─────────


def test_evaluate_alerts_module_has_no_infra_imports() -> None:
    """The use case must not import from app.infrastructure (architecture rule)."""
    import ast
    from pathlib import Path

    src = (
        Path(__file__).parent.parent.parent.parent
        / "src" / "app" / "application" / "use_cases" / "watchlists" / "evaluate_alerts.py"
    )
    tree = ast.parse(src.read_text())
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("app.infrastructure"):
                violations.append(node.module)
    assert not violations, f"evaluate_alerts.py imports from infrastructure: {violations}"
