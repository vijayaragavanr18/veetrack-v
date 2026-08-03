"""Use case: plan the next pull batch for a set of watched entities.

Two execution paths:

  FAST PATH  — no quota constraints and all entities have healthy activity:
    Returns a deterministic plan (round-robin by watchlist priority, no LLM call).

  AGENTIC PATH  — quota is constrained OR any entity has thin/missing results:
    Runs the shared AgentLoop with watcher-specific tools and prompt.
    The agent may inspect activity, quota, aliases, and priorities before
    producing a ranked pull_plan.

  FALLBACK  — if the agentic loop raises AgentDidNotConvergeError:
    Falls back to the fast-path deterministic plan so no entity is silently skipped.

Zero infrastructure imports — receives plain data and calls LLMGateway via Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from app.application.use_cases.shared.agent_loop import (
    AgentDidNotConvergeError,
    AgentLoop,
    ToolCallable,
)
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

# Fraction of total quota remaining below which we consider the source constrained.
QUOTA_CONSTRAINED_THRESHOLD: float = 0.25

# An entity is considered "thin" if its hourly average in the last 6h is this low.
THIN_ACTIVITY_THRESHOLD: float = 0.5


# ── Domain types ─────────────────────────────────────────────────────────────


@dataclass
class WatchedEntity:
    """Lightweight descriptor for a watched entity, passed in by the Celery task."""
    entity_id: str
    source_id: str
    # Hourly average article count in the last 6 hours (pre-computed by caller).
    recent_avg_hourly: float = 0.0
    # Sensitivity of the highest-priority watchlist tracking this entity.
    max_sensitivity: str = "medium"


@dataclass
class PullItem:
    entity_id: str
    source_id: str
    priority: int
    use_aliases: bool
    justification: str


@dataclass
class PullBatchPlan:
    items: list[PullItem] = field(default_factory=list)
    skipped_entity_ids: list[str] = field(default_factory=list)
    agent_path: str = "fast_path"
    reasoning: str = ""


# ── Fast-path helpers ─────────────────────────────────────────────────────────

_SENSITIVITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _is_constrained(
    entities: list[WatchedEntity],
    quota_remaining: int,
    quota_total: int,
) -> bool:
    """Return True when quota is tight relative to the number of entities."""
    if quota_total <= 0:
        return True
    frac_remaining = quota_remaining / quota_total
    if frac_remaining < QUOTA_CONSTRAINED_THRESHOLD:
        return True
    return False


def _has_thin_entities(entities: list[WatchedEntity]) -> bool:
    return any(e.recent_avg_hourly < THIN_ACTIVITY_THRESHOLD for e in entities)


def _fast_plan(entities: list[WatchedEntity]) -> PullBatchPlan:
    """Deterministic plan: sort by watchlist sensitivity, assign sequential priority."""
    sorted_entities = sorted(
        entities,
        key=lambda e: (_SENSITIVITY_ORDER.get(e.max_sensitivity, 99), e.entity_id),
    )
    items = [
        PullItem(
            entity_id=e.entity_id,
            source_id=e.source_id,
            priority=i + 1,
            use_aliases=e.recent_avg_hourly < THIN_ACTIVITY_THRESHOLD,
            justification="routine pull; sorted by watchlist sensitivity",
        )
        for i, e in enumerate(sorted_entities)
    ]
    return PullBatchPlan(items=items, agent_path="fast_path")


# ── Use case ──────────────────────────────────────────────────────────────────


class PlanPullBatch:
    """Plan which entities to pull next and in what order.

    Parameters
    ----------
    gateway:
        LLMGateway used by the agentic path.  Pass None to force fast-path always.
    tools:
        Dict of tool_name → async callable for the agentic loop.
    system_prompt:
        Override for the agentic watcher system prompt (mainly for tests).
    """

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        tools: dict[str, ToolCallable] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._gateway = gateway
        self._tools: dict[str, ToolCallable] = tools or {}
        self._system_prompt = system_prompt

    async def execute(
        self,
        entities: list[WatchedEntity],
        quota_remaining: int,
        quota_total: int,
        source_id: str = "",
    ) -> PullBatchPlan:
        """Produce a pull plan for *entities*.

        Parameters
        ----------
        entities:
            Entities to schedule, each with pre-computed activity stats.
        quota_remaining, quota_total:
            Current window quota for the shared source.  quota_total=0 means
            no limit is tracked (treat as unconstrained).
        source_id:
            The source identifier (used in the agentic initial message for context).
        """
        if not entities:
            return PullBatchPlan()

        if quota_total > 0 and quota_remaining <= 0:
            # Quota fully exhausted — skip everything
            logger.warning(
                "plan_pull_batch.quota_exhausted",
                source_id=source_id,
                quota_total=quota_total,
            )
            return PullBatchPlan(
                skipped_entity_ids=[e.entity_id for e in entities],
                agent_path="fast_path",
                reasoning="Quota exhausted — all entities skipped this window.",
            )

        use_agentic = (
            self._gateway is not None
            and (
                _is_constrained(entities, quota_remaining, quota_total)
                or _has_thin_entities(entities)
            )
        )

        if not use_agentic:
            return _fast_plan(entities)

        plan = await self._run_agentic(entities, quota_remaining, quota_total, source_id)
        return plan

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _run_agentic(
        self,
        entities: list[WatchedEntity],
        quota_remaining: int,
        quota_total: int,
        source_id: str,
    ) -> PullBatchPlan:
        from app.application.use_cases.ingestion.prompts.agentic_watcher import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )

        system = self._system_prompt or SYSTEM_PROMPT
        loop = AgentLoop(
            gateway=self._gateway,  # type: ignore[arg-type]
            system_prompt=system,
            tool_names=TOOL_NAMES,
            tools=self._tools,
            max_iterations=5,
            max_tokens_per_step=800,
            agent_name="watcher_agent",
        )

        entity_summaries = "\n".join(
            f"  - entity_id={e.entity_id!r}  source={e.source_id!r}"
            f"  sensitivity={e.max_sensitivity}  recent_avg={e.recent_avg_hourly:.1f}/h"
            for e in entities
        )
        initial_msg = (
            f"Source: {source_id!r}\n"
            f"Quota remaining: {quota_remaining}/{quota_total}\n\n"
            f"Entities to schedule ({len(entities)} total):\n{entity_summaries}\n\n"
            "Produce a pull_plan that orders these entities by priority given the\n"
            "quota constraints. Use tools to gather more context where needed."
        )

        try:
            loop_result = await loop.run(
                initial_msg, run_id=f"watcher:{source_id}"
            )
        except AgentDidNotConvergeError as exc:
            logger.warning(
                "plan_pull_batch.agent_did_not_converge",
                source_id=source_id,
                error=str(exc),
            )
            return _fast_plan(entities)
        except Exception as exc:
            logger.error(
                "plan_pull_batch.agent_failed",
                source_id=source_id,
                error=str(exc),
            )
            return _fast_plan(entities)

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning(
                "plan_pull_batch.invalid_final_answer",
                source_id=source_id,
                error=str(ve),
            )
            return _fast_plan(entities)

        items = [
            PullItem(
                entity_id=item["entity_id"],
                source_id=item["source_id"],
                priority=item["priority"],
                use_aliases=bool(item.get("use_aliases", False)),
                justification=item.get("justification", ""),
            )
            for item in final.get("pull_plan", [])
        ]
        items.sort(key=lambda x: x.priority)

        return PullBatchPlan(
            items=items,
            skipped_entity_ids=list(final.get("skipped_entities") or []),
            agent_path="agentic",
            reasoning=str(final.get("reasoning", "")),
        )
