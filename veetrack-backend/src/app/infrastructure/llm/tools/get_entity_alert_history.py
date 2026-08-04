"""Tool: get_entity_alert_history.

Returns how many alerts have already been sent for an entity in a recent window,
and the urgency/channel of each, so the agent can assess alert-fatigue risk.

Read-only — never sends a notification.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# DbQuery matches the signature used throughout the workers layer.
DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_entity_alert_history(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return recent alert history for *entity_id* within the last *hours* hours.

    Args dict keys:
        entity_id (str): The entity to look up.
        hours (int, optional): Look-back window in hours (default 24).
    """
    entity_id = str(args.get("entity_id", ""))
    hours = max(1, int(args.get("hours", 24)))

    rows = await db_query(
        """
        SELECT a.id, a.channel, a.status, a.sent_at,
               w.entity_id
        FROM alerts a
        JOIN watchlists w ON w.id = a.watchlist_id
        WHERE w.entity_id = :eid
          AND a.sent_at >= NOW() - INTERVAL ':hours hours'
        ORDER BY a.sent_at DESC
        LIMIT 20
        """,
        {"eid": entity_id, "hours": hours},
    )

    if not rows:
        return f"No alerts fired for this entity in the past {hours} hours."

    lines = [f"Alerts for entity {entity_id!r} in last {hours}h: {len(rows)} total"]
    for r in rows[:10]:
        lines.append(
            f"  - sent_at={r.get('sent_at','?')} channel={r.get('channel','?')} "
            f"status={r.get('status','?')}"
        )
    return "\n".join(lines)
