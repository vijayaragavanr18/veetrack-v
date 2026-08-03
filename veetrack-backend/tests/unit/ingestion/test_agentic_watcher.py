"""Unit tests for the agentic watcher agent (Phase 07-10 revised).

Tests cover:
  - Fast-path vs agentic routing (quota constraints, thin activity).
  - Each new tool function (get_entity_recent_activity, get_source_quota_status,
    get_entity_aliases, get_watchlist_priority) against a fake DB query.
  - Fallback behavior when AgentLoop raises AgentDidNotConvergeError.
  - Full agentic path: agent calls a tool, then produces a pull_plan.
  - validate_final_answer coverage: valid, missing fields, duplicate priority.
  - Quota exhausted: all entities skipped.
  - Empty entity list: returns empty plan immediately.

No infrastructure imports. All I/O via fakes.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.application.use_cases.ingestion.plan_pull_batch import (
    PlanPullBatch,
    PullBatchPlan,
    WatchedEntity,
    _fast_plan,
    _has_thin_entities,
    _is_constrained,
    QUOTA_CONSTRAINED_THRESHOLD,
    THIN_ACTIVITY_THRESHOLD,
)
from app.application.use_cases.ingestion.prompts.agentic_watcher import validate_final_answer
from app.application.use_cases.shared.agent_loop import AgentDidNotConvergeError


# ── Fake LLM Gateway ──────────────────────────────────────────────────────────


class FakeGateway:
    """Minimal fake that returns scripted responses.

    AgentLoop calls: gateway.complete(full_prompt_str, system=..., max_tokens=..., temperature=...)
    and accesses gateway.model_name.
    """

    model_name: str = "fake-model"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._calls: list[Any] = []

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        self._calls.append({"prompt": prompt, **kwargs})
        if not self._responses:
            raise ValueError("FakeGateway: no more scripted responses")
        return self._responses.pop(0)

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        import json
        raw = await self.complete(prompt, system=system, max_tokens=max_tokens)
        return json.loads(raw)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entity(
    entity_id: str = "ent-1",
    source_id: str = "newsdata-default",
    recent_avg_hourly: float = 2.0,
    max_sensitivity: str = "medium",
) -> WatchedEntity:
    return WatchedEntity(
        entity_id=entity_id,
        source_id=source_id,
        recent_avg_hourly=recent_avg_hourly,
        max_sensitivity=max_sensitivity,
    )


def _final_answer_response(
    entity_id: str = "ent-1",
    source_id: str = "newsdata-default",
    priority: int = 1,
    use_aliases: bool = False,
) -> str:
    return json.dumps({
        "type": "final_answer",
        "reasoning": "entity is high-priority, quota has room",
        "pull_plan": [
            {
                "entity_id": entity_id,
                "source_id": source_id,
                "priority": priority,
                "use_aliases": use_aliases,
                "justification": "spiking activity",
            }
        ],
        "skipped_entities": [],
    })


# ── Unit: routing helpers ─────────────────────────────────────────────────────


class TestIsConstrained:
    def test_no_quota_tracking(self) -> None:
        entities = [_make_entity()]
        assert _is_constrained(entities, 10, 0) is True  # quota_total=0 → constrained

    def test_below_threshold(self) -> None:
        # 5/100 = 5% remaining — below 25% threshold
        assert _is_constrained([_make_entity()], quota_remaining=5, quota_total=100) is True

    def test_above_threshold(self) -> None:
        # 80/100 = 80% remaining — healthy
        assert _is_constrained([_make_entity()], quota_remaining=80, quota_total=100) is False

    def test_exactly_at_threshold(self) -> None:
        # 25/100 = 25% — not strictly below, so not constrained
        assert _is_constrained([_make_entity()], quota_remaining=25, quota_total=100) is False


class TestHasThinEntities:
    def test_all_healthy(self) -> None:
        entities = [_make_entity(recent_avg_hourly=2.0), _make_entity(recent_avg_hourly=3.0)]
        assert _has_thin_entities(entities) is False

    def test_one_thin(self) -> None:
        entities = [_make_entity(recent_avg_hourly=0.1), _make_entity(recent_avg_hourly=3.0)]
        assert _has_thin_entities(entities) is True

    def test_zero_activity(self) -> None:
        entities = [_make_entity(recent_avg_hourly=0.0)]
        assert _has_thin_entities(entities) is True


# ── Unit: fast_plan ───────────────────────────────────────────────────────────


class TestFastPlan:
    def test_sorted_by_sensitivity(self) -> None:
        entities = [
            _make_entity("ent-low", max_sensitivity="low"),
            _make_entity("ent-crit", max_sensitivity="critical"),
            _make_entity("ent-med", max_sensitivity="medium"),
        ]
        plan = _fast_plan(entities)
        assert plan.agent_path == "fast_path"
        assert plan.items[0].entity_id == "ent-crit"
        assert plan.items[-1].entity_id == "ent-low"

    def test_priorities_are_sequential(self) -> None:
        entities = [_make_entity(f"ent-{i}") for i in range(3)]
        plan = _fast_plan(entities)
        priorities = [item.priority for item in plan.items]
        assert priorities == [1, 2, 3]

    def test_thin_entity_gets_use_aliases(self) -> None:
        entities = [_make_entity("thin", recent_avg_hourly=0.1)]
        plan = _fast_plan(entities)
        assert plan.items[0].use_aliases is True

    def test_healthy_entity_no_aliases(self) -> None:
        entities = [_make_entity("healthy", recent_avg_hourly=5.0)]
        plan = _fast_plan(entities)
        assert plan.items[0].use_aliases is False


# ── Unit: PlanPullBatch — fast path routing ───────────────────────────────────


@pytest.mark.asyncio
class TestPlanPullBatchFastPath:
    async def test_empty_entities_returns_empty_plan(self) -> None:
        uc = PlanPullBatch()
        plan = await uc.execute(entities=[], quota_remaining=100, quota_total=200)
        assert plan.items == []
        assert plan.skipped_entity_ids == []

    async def test_quota_exhausted_skips_all(self) -> None:
        uc = PlanPullBatch()
        entities = [_make_entity("ent-1"), _make_entity("ent-2")]
        plan = await uc.execute(entities=entities, quota_remaining=0, quota_total=100)
        assert plan.items == []
        assert len(plan.skipped_entity_ids) == 2
        assert plan.agent_path == "fast_path"

    async def test_healthy_quota_no_thin_entities_goes_fast(self) -> None:
        uc = PlanPullBatch()  # no gateway
        entities = [_make_entity(recent_avg_hourly=3.0)]
        plan = await uc.execute(entities=entities, quota_remaining=80, quota_total=100)
        assert plan.agent_path == "fast_path"
        assert len(plan.items) == 1

    async def test_no_gateway_forces_fast_path_even_with_thin_entity(self) -> None:
        uc = PlanPullBatch(gateway=None)
        entities = [_make_entity(recent_avg_hourly=0.0)]
        plan = await uc.execute(entities=entities, quota_remaining=80, quota_total=100)
        assert plan.agent_path == "fast_path"


# ── Unit: PlanPullBatch — agentic path ───────────────────────────────────────


@pytest.mark.asyncio
class TestPlanPullBatchAgenticPath:
    async def test_constrained_quota_triggers_agentic(self) -> None:
        """When quota is tight, use the agentic path and return the agent's plan."""
        gateway = FakeGateway(responses=[_final_answer_response()])
        uc = PlanPullBatch(gateway=gateway)
        entities = [_make_entity("ent-1")]
        plan = await uc.execute(entities=entities, quota_remaining=5, quota_total=100)
        assert plan.agent_path == "agentic"
        assert len(plan.items) == 1
        assert plan.items[0].entity_id == "ent-1"

    async def test_thin_activity_triggers_agentic(self) -> None:
        gateway = FakeGateway(responses=[_final_answer_response()])
        uc = PlanPullBatch(gateway=gateway)
        entities = [_make_entity("ent-1", recent_avg_hourly=0.0)]
        plan = await uc.execute(entities=entities, quota_remaining=90, quota_total=100)
        assert plan.agent_path == "agentic"

    async def test_agentic_plan_preserves_use_aliases_flag(self) -> None:
        resp = json.dumps({
            "type": "final_answer",
            "reasoning": "thin entity",
            "pull_plan": [{
                "entity_id": "ent-1",
                "source_id": "newsdata-default",
                "priority": 1,
                "use_aliases": True,
                "justification": "alias broadening needed",
            }],
            "skipped_entities": [],
        })
        gateway = FakeGateway(responses=[resp])
        uc = PlanPullBatch(gateway=gateway)
        entities = [_make_entity("ent-1", recent_avg_hourly=0.0)]
        plan = await uc.execute(entities=entities, quota_remaining=90, quota_total=100)
        assert plan.items[0].use_aliases is True

    async def test_skipped_entities_propagated(self) -> None:
        resp = json.dumps({
            "type": "final_answer",
            "reasoning": "quota tight",
            "pull_plan": [{
                "entity_id": "ent-1",
                "source_id": "newsdata-default",
                "priority": 1,
                "use_aliases": False,
                "justification": "critical priority",
            }],
            "skipped_entities": ["ent-2", "ent-3"],
            "skip_reason": "quota exhausted for lower-priority entities",
        })
        gateway = FakeGateway(responses=[resp])
        uc = PlanPullBatch(gateway=gateway)
        entities = [
            _make_entity("ent-1", max_sensitivity="critical"),
            _make_entity("ent-2", max_sensitivity="low"),
            _make_entity("ent-3", max_sensitivity="low"),
        ]
        plan = await uc.execute(entities=entities, quota_remaining=3, quota_total=100)
        assert plan.skipped_entity_ids == ["ent-2", "ent-3"]

    async def test_items_sorted_by_priority(self) -> None:
        resp = json.dumps({
            "type": "final_answer",
            "reasoning": "two entities",
            "pull_plan": [
                {
                    "entity_id": "ent-2",
                    "source_id": "newsdata-default",
                    "priority": 2,
                    "use_aliases": False,
                    "justification": "medium priority",
                },
                {
                    "entity_id": "ent-1",
                    "source_id": "newsdata-default",
                    "priority": 1,
                    "use_aliases": False,
                    "justification": "high priority",
                },
            ],
        })
        gateway = FakeGateway(responses=[resp])
        uc = PlanPullBatch(gateway=gateway)
        entities = [_make_entity("ent-1"), _make_entity("ent-2")]
        plan = await uc.execute(entities=entities, quota_remaining=5, quota_total=100)
        assert plan.items[0].entity_id == "ent-1"
        assert plan.items[1].entity_id == "ent-2"


# ── Unit: fallback behavior ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPlanPullBatchFallback:
    async def test_agent_did_not_converge_falls_back_to_fast_plan(self) -> None:
        gateway = FakeGateway(responses=[])  # will cause error

        with patch(
            "app.application.use_cases.ingestion.plan_pull_batch.AgentLoop"
        ) as MockLoop:
            mock_instance = AsyncMock()
            mock_instance.run.side_effect = AgentDidNotConvergeError("no convergence")
            MockLoop.return_value = mock_instance

            uc = PlanPullBatch(gateway=gateway)
            entities = [_make_entity("ent-1")]
            plan = await uc.execute(entities=entities, quota_remaining=5, quota_total=100)

        assert plan.agent_path == "fast_path"
        assert len(plan.items) == 1

    async def test_unexpected_exception_falls_back_to_fast_plan(self) -> None:
        with patch(
            "app.application.use_cases.ingestion.plan_pull_batch.AgentLoop"
        ) as MockLoop:
            mock_instance = AsyncMock()
            mock_instance.run.side_effect = RuntimeError("network error")
            MockLoop.return_value = mock_instance

            uc = PlanPullBatch(gateway=FakeGateway([]))
            entities = [_make_entity("ent-1")]
            plan = await uc.execute(entities=entities, quota_remaining=5, quota_total=100)

        assert plan.agent_path == "fast_path"

    async def test_invalid_final_answer_falls_back(self) -> None:
        # Returns a final answer missing required fields
        bad_response = json.dumps({"type": "final_answer", "reasoning": "ok"})  # missing pull_plan
        gateway = FakeGateway(responses=[bad_response])
        uc = PlanPullBatch(gateway=gateway)
        entities = [_make_entity("ent-1")]
        plan = await uc.execute(entities=entities, quota_remaining=5, quota_total=100)
        assert plan.agent_path == "fast_path"


# ── Unit: validate_final_answer ───────────────────────────────────────────────


class TestValidateFinalAnswer:
    def test_valid_single_item(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "test",
            "pull_plan": [{
                "entity_id": "e1",
                "source_id": "s1",
                "priority": 1,
                "use_aliases": False,
                "justification": "reason",
            }],
        }
        validate_final_answer(step)  # should not raise

    def test_valid_empty_pull_plan(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "nothing to pull",
            "pull_plan": [],
            "skipped_entities": ["e1"],
        }
        validate_final_answer(step)

    def test_wrong_type(self) -> None:
        with pytest.raises(ValueError, match='Expected type="final_answer"'):
            validate_final_answer({"type": "tool_call", "pull_plan": []})

    def test_missing_pull_plan(self) -> None:
        with pytest.raises(ValueError, match='"pull_plan" must be a list'):
            validate_final_answer({"type": "final_answer", "reasoning": "x"})

    def test_item_missing_entity_id(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "x",
            "pull_plan": [{
                "source_id": "s1",
                "priority": 1,
                "use_aliases": False,
                "justification": "ok",
            }],
        }
        with pytest.raises(ValueError, match='"entity_id"'):
            validate_final_answer(step)

    def test_item_invalid_priority(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "x",
            "pull_plan": [{
                "entity_id": "e1",
                "source_id": "s1",
                "priority": 0,
                "use_aliases": False,
                "justification": "ok",
            }],
        }
        with pytest.raises(ValueError, match="positive integer"):
            validate_final_answer(step)

    def test_duplicate_priority(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "x",
            "pull_plan": [
                {
                    "entity_id": "e1",
                    "source_id": "s1",
                    "priority": 1,
                    "use_aliases": False,
                    "justification": "ok",
                },
                {
                    "entity_id": "e2",
                    "source_id": "s1",
                    "priority": 1,
                    "use_aliases": False,
                    "justification": "ok",
                },
            ],
        }
        with pytest.raises(ValueError, match="Duplicate priority"):
            validate_final_answer(step)

    def test_use_aliases_not_bool(self) -> None:
        step = {
            "type": "final_answer",
            "reasoning": "x",
            "pull_plan": [{
                "entity_id": "e1",
                "source_id": "s1",
                "priority": 1,
                "use_aliases": "yes",
                "justification": "ok",
            }],
        }
        with pytest.raises(ValueError, match="use_aliases.*bool"):
            validate_final_answer(step)


# ── Unit: tool functions with fake DB query ───────────────────────────────────


@pytest.mark.asyncio
class TestGetEntityRecentActivity:
    async def test_no_rows_returns_quiet_signal(self) -> None:
        from app.infrastructure.llm.tools.get_entity_recent_activity import (
            get_entity_recent_activity,
        )

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_entity_recent_activity({"entity_id": "e1", "hours": 24}, _q)
        assert "quiet" in result.lower() or "no articles" in result.lower()

    async def test_spiking_signal(self) -> None:
        from app.infrastructure.llm.tools.get_entity_recent_activity import (
            get_entity_recent_activity,
        )

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"hour_bucket": "2026-07-21 10:00:00", "article_count": 10}] * 6

        result = await get_entity_recent_activity({"entity_id": "e1", "hours": 24}, _q)
        assert "spike" in result.lower() or "high activity" in result.lower() or "spiking" in result.lower()


@pytest.mark.asyncio
class TestGetSourceQuotaStatus:
    async def test_no_rows(self) -> None:
        from app.infrastructure.llm.tools.get_source_quota_status import get_source_quota_status

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_source_quota_status({"source_id": "newsdata-default"}, _q)
        assert "no usage" in result.lower() or "newsdata-default" in result

    async def test_quota_exhausted(self) -> None:
        from app.infrastructure.llm.tools.get_source_quota_status import get_source_quota_status

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"calls_made": 100, "quota_limit": 100, "window_start": "2026-07-21 10:00:00"}]

        result = await get_source_quota_status({"source_id": "newsdata-default"}, _q)
        assert "exhausted" in result.lower() or "remaining=0" in result

    async def test_quota_healthy(self) -> None:
        from app.infrastructure.llm.tools.get_source_quota_status import get_source_quota_status

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"calls_made": 10, "quota_limit": 100, "window_start": "2026-07-21 10:00:00"}]

        result = await get_source_quota_status({"source_id": "newsdata-default"}, _q)
        assert "healthy" in result.lower() or "remaining=90" in result


@pytest.mark.asyncio
class TestGetEntityAliases:
    async def test_no_entity(self) -> None:
        from app.infrastructure.llm.tools.get_entity_aliases import get_entity_aliases

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_entity_aliases({"entity_id": "missing"}, _q)
        assert "no entity" in result.lower() or "missing" in result

    async def test_with_aliases(self) -> None:
        from app.infrastructure.llm.tools.get_entity_aliases import get_entity_aliases

        call_count = 0

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"canonical_name": "Apple Inc.", "entity_type": "org"}]
            return [{"alias": "Apple"}, {"alias": "AAPL"}]

        result = await get_entity_aliases({"entity_id": "ent-apple"}, _q)
        assert "Apple Inc." in result
        assert "alias_count=2" in result

    async def test_no_aliases_suggests_broadening(self) -> None:
        from app.infrastructure.llm.tools.get_entity_aliases import get_entity_aliases

        call_count = 0

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [{"canonical_name": "Obscure Corp", "entity_type": "org"}]
            return []

        result = await get_entity_aliases({"entity_id": "ent-obs"}, _q)
        assert "alias_count=0" in result
        assert "broadening" in result.lower() or "no aliases" in result.lower()


@pytest.mark.asyncio
class TestGetWatchlistPriority:
    async def test_no_watchlists(self) -> None:
        from app.infrastructure.llm.tools.get_watchlist_priority import get_watchlist_priority

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_watchlist_priority({"entity_id": "ent-1"}, _q)
        assert "no active watchlists" in result.lower() or "not tracked" in result.lower()

    async def test_critical_watchlist_surfaces_priority(self) -> None:
        from app.infrastructure.llm.tools.get_watchlist_priority import get_watchlist_priority

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{
                "watchlist_id": "wl-1",
                "watchlist_name": "CEO Tracker",
                "sensitivity": "critical",
                "workspace_id": "ws-1",
                "entity_count": 5,
            }]

        result = await get_watchlist_priority({"entity_id": "ent-1"}, _q)
        assert "critical" in result.lower()
        assert "prioritis" in result.lower()

    async def test_multiple_watchlists_highest_sensitivity_reported(self) -> None:
        from app.infrastructure.llm.tools.get_watchlist_priority import get_watchlist_priority

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {"watchlist_id": "wl-1", "watchlist_name": "A", "sensitivity": "low",
                 "workspace_id": "ws-1", "entity_count": 2},
                {"watchlist_id": "wl-2", "watchlist_name": "B", "sensitivity": "high",
                 "workspace_id": "ws-1", "entity_count": 3},
            ]

        result = await get_watchlist_priority({"entity_id": "ent-1"}, _q)
        assert "highest_sensitivity='high'" in result


# ── Architecture check ────────────────────────────────────────────────────────


class TestArchitecture:
    def test_plan_pull_batch_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/ingestion/plan_pull_batch.py"
        )
        tree = ast.parse(src.read_text())
        bad_prefixes = ("app.infrastructure", "sqlalchemy", "fastapi", "redis")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    for bad in bad_prefixes:
                        assert not (name or "").startswith(bad), (
                            f"plan_pull_batch imports from {name!r} (infra import violation)"
                        )

    def test_agentic_watcher_prompt_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/ingestion/prompts/agentic_watcher.py"
        )
        tree = ast.parse(src.read_text())
        bad_prefixes = ("app.infrastructure", "sqlalchemy", "fastapi", "redis")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    for bad in bad_prefixes:
                        assert not (name or "").startswith(bad), (
                            f"agentic_watcher prompt imports from {name!r} (infra import violation)"
                        )
