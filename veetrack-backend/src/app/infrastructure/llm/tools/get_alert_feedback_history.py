"""Tool: get_alert_feedback_history.

Returns the ratio of useful vs not_useful feedback for past alerts on this
entity, so the agent can weigh whether alerts for this entity actually land
with users.  Null-feedback (no response) is neutral — not counted as useful
or not_useful, so the agent isn't penalised for users who simply never mark
anything.

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_alert_feedback_history(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return feedback statistics for past alerts related to *entity_id*.

    Args dict keys:
        entity_id (str): The entity whose alert feedback to inspect.
    """
    entity_id = str(args.get("entity_id", ""))

    rows = await db_query(
        """
        SELECT a.user_feedback, COUNT(*) AS cnt
        FROM alerts a
        JOIN watchlists w ON w.id = a.watchlist_id
        WHERE w.entity_id = :eid
          AND a.user_feedback IS NOT NULL
        GROUP BY a.user_feedback
        """,
        {"eid": entity_id},
    )

    if not rows:
        return (
            f"No feedback data for entity {entity_id!r}. "
            "Treat as neutral — no prior signal either way."
        )

    counts: dict[str, int] = {}
    for r in rows:
        feedback = str(r.get("user_feedback") or "unknown")
        counts[feedback] = int(r.get("cnt") or 0)

    useful = counts.get("useful", 0)
    not_useful = counts.get("not_useful", 0)
    total = useful + not_useful

    if total == 0:
        return f"No marked feedback for entity {entity_id!r}."

    pct_useful = round(useful / total * 100)
    lines = [
        f"Alert feedback for entity {entity_id!r}: {total} marked responses",
        f"  useful={useful} ({pct_useful}%)  not_useful={not_useful} ({100-pct_useful}%)",
    ]
    if not_useful > useful:
        lines.append(
            "  ⚠ Majority of past alerts for this entity were marked not_useful — "
            "apply stricter alerting threshold."
        )
    elif useful > not_useful:
        lines.append(
            "  ✓ Majority of past alerts for this entity were marked useful — "
            "alerts are landing well."
        )
    return "\n".join(lines)
