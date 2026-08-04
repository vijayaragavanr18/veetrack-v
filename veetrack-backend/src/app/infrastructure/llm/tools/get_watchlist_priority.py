"""Tool: get_watchlist_priority.

Returns priority metadata for all watchlists tracking a given entity so the
agent can rank pull order when API quota is constrained.

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_watchlist_priority(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return priority info for watchlists that track *entity_id*.

    Args dict keys:
        entity_id (str): The entity to look up.
    """
    entity_id = str(args.get("entity_id", ""))

    rows = await db_query(
        """
        SELECT
            w.id             AS watchlist_id,
            w.name           AS watchlist_name,
            w.sensitivity    AS sensitivity,
            w.workspace_id   AS workspace_id,
            COUNT(we.entity_id) FILTER (WHERE we.entity_id IS NOT NULL) AS entity_count
        FROM watchlists w
        JOIN watchlist_entities we_target
          ON we_target.watchlist_id = w.id AND we_target.entity_id = :eid
        LEFT JOIN watchlist_entities we
          ON we.watchlist_id = w.id
        WHERE w.deleted_at IS NULL
        GROUP BY w.id, w.name, w.sensitivity, w.workspace_id
        ORDER BY
            CASE w.sensitivity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                ELSE 4
            END,
            w.name
        """,
        {"eid": entity_id},
    )

    if not rows:
        return (
            f"No active watchlists found for entity {entity_id!r}. "
            "Entity may not be tracked by any workspace."
        )

    lines = [f"Watchlists tracking entity {entity_id!r} ({len(rows)} total):"]
    for r in rows:
        sensitivity = str(r.get("sensitivity") or "medium")
        entity_count = int(r.get("entity_count") or 0)
        lines.append(
            f"  - {r.get('watchlist_name')!r}  id={r.get('watchlist_id')}"
            f"  sensitivity={sensitivity}  entities_in_list={entity_count}"
            f"  workspace={r.get('workspace_id')}"
        )

    # Surface the highest-sensitivity level seen
    sensitivities = [str(r.get("sensitivity") or "medium") for r in rows]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    highest = min(sensitivities, key=lambda s: order.get(s, 99))
    lines.append(f"  highest_sensitivity={highest!r}")
    if highest == "critical":
        lines.append("  → At least one critical-sensitivity watchlist: this entity should be prioritised even under quota constraints.")
    elif highest == "high":
        lines.append("  → High-sensitivity watchlist present: prefer this entity over medium/low peers.")
    return "\n".join(lines)
