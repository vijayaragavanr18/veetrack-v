"""Tool: get_article_publish_gap.

Returns the time gap between two articles' published_at timestamps.
A same-day near-duplicate reads very differently from one published three days
later — the agent uses this to distinguish wire-service updates (hours apart)
from genuine follow-up coverage (days apart).

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_article_publish_gap(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return the time gap between articles *article_id_a* and *article_id_b*.

    Args dict keys:
        article_id_a (str): The new article being evaluated.
        article_id_b (str): The candidate duplicate article.
    """
    id_a = str(args.get("article_id_a", ""))
    id_b = str(args.get("article_id_b", ""))

    rows = await db_query(
        """
        SELECT id, published_at
        FROM articles
        WHERE id IN (:id_a, :id_b)
        ORDER BY published_at ASC
        """,
        {"id_a": id_a, "id_b": id_b},
    )

    if len(rows) < 2:
        found_ids = [str(r.get("id", "")) for r in rows]
        missing = [i for i in (id_a, id_b) if i not in found_ids]
        return f"Could not fetch both articles. Missing ids: {missing}"

    ts_a = rows[0].get("published_at")
    ts_b = rows[1].get("published_at")
    id_early = str(rows[0].get("id", ""))
    id_late = str(rows[1].get("id", ""))

    # Compute gap in seconds via SQL-side subtraction is not available here, so
    # interpret as strings and do a simple comparison.
    gap_line = f"  earlier={id_early!r} at {ts_a}"
    gap_line2 = f"  later={id_late!r} at {ts_b}"

    # Try to compute numeric gap if timestamps are datetime objects
    gap_description = "unknown"
    try:

        def _to_utc(ts: object) -> object:
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:  # type: ignore[union-attr]

                return ts.replace(tzinfo=UTC)  # type: ignore[union-attr]
            return ts

        ta = _to_utc(ts_a)
        tb = _to_utc(ts_b)
        delta = tb - ta  # type: ignore[operator]
        total_seconds = int(delta.total_seconds())  # type: ignore[union-attr]
        if total_seconds < 3600:
            gap_description = f"{total_seconds // 60}m"
        elif total_seconds < 86400:
            gap_description = f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
        else:
            gap_description = f"{total_seconds // 86400}d {(total_seconds % 86400) // 3600}h"
    except Exception:
        pass

    lines = [
        f"Publish gap between {id_a!r} and {id_b!r}: {gap_description}",
        gap_line,
        gap_line2,
    ]
    if gap_description != "unknown":
        total_secs_approx = 0
        try:
            ta2 = _to_utc(ts_a)  # type: ignore[possibly-undefined]
            tb2 = _to_utc(ts_b)  # type: ignore[possibly-undefined]
            total_secs_approx = int((tb2 - ta2).total_seconds())  # type: ignore[operator,union-attr]
        except Exception:
            pass

        if total_secs_approx < 3600:
            lines.append(
                "  ⚡ Same-hour gap — likely a wire-service update or retransmission."
                " Lean toward 'duplicate' or 'update'."
            )
        elif total_secs_approx < 86400:
            lines.append(
                "  ⏱ Same-day gap — could be a follow-up update with new facts."
                " Check content for new information."
            )
        else:
            lines.append(
                "  📅 Multi-day gap — strong signal this is a distinct follow-up,"
                " not a duplicate."
            )

    return "\n".join(lines)
