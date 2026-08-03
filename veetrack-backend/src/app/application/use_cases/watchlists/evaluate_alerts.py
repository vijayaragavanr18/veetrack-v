"""EvaluateAlerts use case — agentic two-tier alert decision engine.

Two execution paths:

  FAST PATH  — unambiguously above threshold AND entity has no recent alerts:
    Alert immediately, no LLM call.  Records agent_path='fast_path'.

  AGENTIC PATH  — borderline cases where judgment helps:
    Runs the shared AgentLoop with alert-specific tools and prompt.
    Records agent_path='agentic' and the full reasoning_trace.

  FALLBACK  — if the agentic loop raises AgentDidNotConvergeError:
    Falls back to the original flat threshold check so no alert that should
    have fired is silently dropped.  Records agent_path='fallback'.

Configurable thresholds (named constants, not magic numbers):
  FAST_PATH_THRESHOLD   — risk levels that always fast-path when no recent alerts.
  BORDERLINE_THRESHOLD  — risk levels that may warrant an agentic check.
  RECENT_ALERT_WINDOW_HOURS  — how many hours define "recent" for fatigue detection.
  RECENT_ALERT_FATIGUE_COUNT — how many alerts in that window trigger the agentic path.
  LOW_CONFIDENCE_THRESHOLD   — rec confidence below this triggers agentic even on medium risk.
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
from app.domain.entities.watchlist import AlertRecord, Watchlist
from app.domain.interfaces.repositories import WatchlistRepository

logger = structlog.get_logger(__name__)

# ── Tunable constants ────────────────────────────────────────────────────────

# Risk levels that take the fast path immediately (no recent alert required).
FAST_PATH_THRESHOLD: frozenset[str] = frozenset({"critical"})

# Risk levels where we bother with an agentic check at all.
BORDERLINE_THRESHOLD: frozenset[str] = frozenset({"high", "medium"})

# Alert fatigue window and count
RECENT_ALERT_WINDOW_HOURS: int = 24
RECENT_ALERT_FATIGUE_COUNT: int = 2

# Recommendation confidence below this triggers agentic path even on medium risk
LOW_CONFIDENCE_THRESHOLD: float = 0.55


def _is_fast_path(
    risk_level: str,
    recent_alert_count: int,
) -> bool:
    """Return True when the decision is unambiguously clear (no LLM needed).

    Fast path fires for:
    - Critical risk with zero recent alerts (no fatigue concern).
    - High risk with zero recent alerts.
    """
    if risk_level in FAST_PATH_THRESHOLD and recent_alert_count == 0:
        return True
    if risk_level == "high" and recent_alert_count == 0:
        return True
    return False


def _is_borderline(
    risk_level: str,
    recent_alert_count: int,
    recommendation_confidence: float | None,
) -> bool:
    """Return True when the case warrants the agentic reasoning path.

    Agentic path triggers for:
    - Any high/critical story when there are already recent alerts (fatigue risk).
    - Medium risk story at all times (never obviously clear-cut).
    - Any story whose latest recommendation had low confidence.
    """
    if risk_level not in BORDERLINE_THRESHOLD and risk_level != "critical":
        return False  # low risk → skip alert entirely, no agentic overhead
    if recent_alert_count >= RECENT_ALERT_FATIGUE_COUNT:
        return True
    if risk_level in {"high", "critical"} and recent_alert_count > 0:
        return True
    if risk_level == "medium":
        return True
    if recommendation_confidence is not None and recommendation_confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    return False


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class AlertEvaluationResult:
    fired: list[AlertRecord] = field(default_factory=list)
    skipped_count: int = 0


# ── LLMGateway protocol (imported via domain interface, not infrastructure) ──

from app.domain.interfaces.services import LLMGateway  # noqa: E402


# ── Use case ─────────────────────────────────────────────────────────────────


class EvaluateAlerts:
    """Evaluate a story against all watchlists tracking its primary entity.

    Parameters
    ----------
    repo:
        WatchlistRepository for alert persistence.
    gateway:
        LLMGateway used by the agentic path.  Pass None to disable the agentic
        path entirely (falls straight to fast-path or flat-threshold fallback).
    tools:
        Dict of tool_name → async callable for the agentic path.
    system_prompt:
        System prompt for the alert agent loop.  Defaults to the canonical
        agentic_alert system prompt.
    """

    def __init__(
        self,
        repo: WatchlistRepository,
        gateway: LLMGateway | None = None,
        tools: dict[str, ToolCallable] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        self._tools: dict[str, ToolCallable] = tools or {}
        self._system_prompt = system_prompt

    async def execute(
        self,
        story_id: str,
        entity_id: str,
        workspace_id: str,
        risk_level: str,
        recent_alert_count: int = 0,
        recommendation_confidence: float | None = None,
    ) -> AlertEvaluationResult:
        """Evaluate watchlists and fire alerts where warranted.

        Parameters
        ----------
        story_id, entity_id, workspace_id, risk_level:
            Basic story/entity context, same as the original Phase 24 signature.
        recent_alert_count:
            Pre-computed count of alerts fired for this entity in the last
            RECENT_ALERT_WINDOW_HOURS hours.  Callers (the Celery task) should
            query this before calling execute() so it stays injectable/testable.
        recommendation_confidence:
            The confidence score of the latest recommendation for this story, or
            None if not yet generated.  Used for the borderline trigger.
        """
        watchlists: list[Watchlist] = await self._repo.list_by_entity_across_workspace(
            entity_id, workspace_id
        )
        result = AlertEvaluationResult()

        # Low risk → never alert, no reasoning needed
        if risk_level == "low":
            result.skipped_count = len(watchlists)
            return result

        use_fast = _is_fast_path(risk_level, recent_alert_count)
        use_agentic = (
            not use_fast
            and self._gateway is not None
            and _is_borderline(risk_level, recent_alert_count, recommendation_confidence)
        )

        for wl in watchlists:
            if use_fast:
                alert = await self._fire_alert(
                    wl, story_id, agent_path="fast_path", reasoning_trace=[], channel=None
                )
                if alert:
                    result.fired.append(alert)
            elif use_agentic:
                alert = await self._run_agentic(wl, story_id, entity_id, risk_level)
                if alert:
                    result.fired.append(alert)
                else:
                    result.skipped_count += 1
            else:
                # Flat threshold fallback: medium or high without agentic gateway
                if risk_level in {"high", "critical"}:
                    alert = await self._fire_alert(
                        wl, story_id, agent_path="fallback", reasoning_trace=[], channel=None
                    )
                    if alert:
                        result.fired.append(alert)
                else:
                    result.skipped_count += 1

        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _fire_alert(
        self,
        wl: Watchlist,
        story_id: str,
        agent_path: str,
        reasoning_trace: list[Any],
        channel: str | None,
    ) -> AlertRecord | None:
        """Persist one alert per enabled channel (or the specified channel)."""
        channels = wl.alert_channels
        fired: AlertRecord | None = None
        for ch, enabled in channels.items():
            if not enabled:
                continue
            if channel is not None and ch != channel:
                continue
            alert = AlertRecord(
                watchlist_id=wl.id,
                story_id=story_id,
                channel=ch,
                status="pending",
                agent_path=agent_path,
                reasoning_trace=reasoning_trace,
            )
            fired = await self._repo.save_alert(alert)
        return fired

    async def _run_agentic(
        self,
        wl: Watchlist,
        story_id: str,
        entity_id: str,
        risk_level: str,
    ) -> AlertRecord | None:
        """Run the AgentLoop for this watchlist/story pair.

        Returns a saved AlertRecord if the agent decides to alert, None if it
        decides to suppress.  Falls back to a flat threshold check if the loop
        fails to converge.
        """
        from app.application.use_cases.watchlists.prompts.agentic_alert import (
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
            max_tokens_per_step=600,
            agent_name="alert_agent",
        )

        initial_msg = (
            f"Story ID: {story_id}\n"
            f"Entity ID: {entity_id}\n"
            f"Watchlist ID: {wl.id}\n"
            f"Risk level: {risk_level}\n\n"
            "Decide whether to alert the watchlist subscriber for this story update.\n"
            "Use tools to gather context, then produce a final_answer."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"{wl.id}:{story_id}")
        except AgentDidNotConvergeError as exc:
            logger.warning(
                "evaluate_alerts.agent_did_not_converge",
                watchlist_id=wl.id,
                story_id=story_id,
                error=str(exc),
            )
            # Fallback: flat threshold — alert on high/critical, suppress medium
            if risk_level in {"high", "critical"}:
                return await self._fire_alert(
                    wl, story_id, agent_path="fallback", reasoning_trace=[], channel=None
                )
            return None
        except Exception as exc:
            logger.error(
                "evaluate_alerts.agent_failed",
                watchlist_id=wl.id,
                story_id=story_id,
                error=str(exc),
            )
            if risk_level in {"high", "critical"}:
                return await self._fire_alert(
                    wl, story_id, agent_path="fallback", reasoning_trace=[], channel=None
                )
            return None

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning(
                "evaluate_alerts.invalid_final_answer",
                watchlist_id=wl.id,
                story_id=story_id,
                error=str(ve),
            )
            if risk_level in {"high", "critical"}:
                return await self._fire_alert(
                    wl, story_id, agent_path="fallback", reasoning_trace=[], channel=None
                )
            return None

        if not final.get("should_alert"):
            logger.info(
                "evaluate_alerts.agentic_suppressed",
                watchlist_id=wl.id,
                story_id=story_id,
                suppress_reason=final.get("suppress_reason", ""),
            )
            return None

        channel = str(final.get("channel") or "websocket")
        # Only fire the channel the agent chose if it's actually enabled
        if not wl.alert_channels.get(channel):
            # Fall back to first enabled channel
            channel = next(
                (ch for ch, on in wl.alert_channels.items() if on),
                "websocket",
            )

        alert = AlertRecord(
            watchlist_id=wl.id,
            story_id=story_id,
            channel=channel,
            status="pending",
            agent_path="agentic",
            reasoning_trace=loop_result.trace,
        )
        saved = await self._repo.save_alert(alert)
        logger.info(
            "evaluate_alerts.agentic_fired",
            watchlist_id=wl.id,
            story_id=story_id,
            channel=channel,
            urgency=final.get("urgency"),
            iterations=loop_result.iterations_used,
        )
        return saved
