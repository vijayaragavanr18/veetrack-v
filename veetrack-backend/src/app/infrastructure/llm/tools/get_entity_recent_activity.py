"""Tool: get_entity_recent_activity.

Returns result counts from recent pulls for an entity, so the agent can spot
entities going quiet (thin results → consider broadening query) vs. spiking
(many results → high-priority refresh).

Read-only.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_entity_recent_activity(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return recent article ingestion counts for *entity_id*.

    Args dict keys:
        entity_id (str): The entity to inspect.
        hours (int, optional): Look-back window in hours (default 48).
    """
    entity_id = str(args.get("entity_id", ""))
    hours = max(1, int(args.get("hours", 48)))

    rows = await db_query(
        """
        SELECT
            DATE_TRUNC('hour', a.ingested_at) AS hour_bucket,
            COUNT(*) AS article_count
        FROM articles a
        JOIN article_entities ae ON ae.article_id = a.id
        WHERE ae.entity_id = :eid
          AND a.ingested_at >= NOW() - INTERVAL ':hours hours'
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 24
        """,
        {"eid": entity_id, "hours": hours},
    )

    total = sum(int(r.get("article_count") or 0) for r in rows)

    if not rows:
        return (
            f"No articles ingested for entity {entity_id!r} in the past {hours}h. "
            "Entity may be going quiet — consider broadening query with aliases."
        )

    recent_hourly = [int(r.get("article_count") or 0) for r in rows[:6]]
    avg_recent = sum(recent_hourly) / max(len(recent_hourly), 1)

    lines = [
        f"Entity {entity_id!r} — {total} articles in last {hours}h",
        f"  last_6h_avg={avg_recent:.1f}/h",
    ]
    if avg_recent == 0:
        lines.append("  ⚠ Zero articles in the last 6 hours — possible quiet period or query miss.")
    elif avg_recent > 5:
        lines.append("  📈 High activity — entity is spiking, prioritise refresh.")
    return "\n".join(lines)
