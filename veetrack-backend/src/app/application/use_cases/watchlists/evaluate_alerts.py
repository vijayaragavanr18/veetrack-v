"""EvaluateAlerts use case — checks if a story's risk triggers watchlist alerts."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities.watchlist import AlertRecord, Watchlist
from app.domain.interfaces.repositories import WatchlistRepository


@dataclass
class AlertEvaluationResult:
    fired: list[AlertRecord] = field(default_factory=list)
    skipped_count: int = 0


class EvaluateAlerts:
    """Evaluate a story against all watchlists tracking its primary entity.

    An alert fires when the story risk_level is 'high' or 'critical'.
    """

    HIGH_RISK_LEVELS = frozenset({"high", "critical"})

    def __init__(self, repo: WatchlistRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        story_id: str,
        entity_id: str,
        workspace_id: str,
        risk_level: str,
    ) -> AlertEvaluationResult:
        watchlists: list[Watchlist] = await self._repo.list_by_entity_across_workspace(
            entity_id, workspace_id
        )
        result = AlertEvaluationResult()

        if risk_level not in self.HIGH_RISK_LEVELS:
            result.skipped_count = len(watchlists)
            return result

        for wl in watchlists:
            channels: dict[str, object] = wl.alert_channels
            for channel, enabled in channels.items():
                if not enabled:
                    continue
                alert = AlertRecord(
                    watchlist_id=wl.id,
                    story_id=story_id,
                    channel=channel,
                    status="pending",
                )
                saved = await self._repo.save_alert(alert)
                result.fired.append(saved)

        return result
