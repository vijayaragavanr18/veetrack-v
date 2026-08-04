"""Tool: get_source_quota_status.

Returns remaining API budget for a source in the current rate-limit window,
so the agent knows how many calls are actually available before deciding
how to allocate them across competing entities.

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_source_quota_status(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return quota usage for *source_id* in the current window.

    Args dict keys:
        source_id (str): The source to inspect (e.g. 'newsdata-default').
    """
    source_id = str(args.get("source_id", ""))

    rows = await db_query(
        """
        SELECT calls_made, quota_limit, window_start
        FROM api_usage_log
        WHERE source_id = :sid
        ORDER BY window_start DESC
        LIMIT 1
        """,
        {"sid": source_id},
    )

    if not rows:
        return (
            f"No usage data for source {source_id!r}. "
            "Either unused this window or source ID is wrong."
        )

    r = rows[0]
    calls_made = int(r.get("calls_made") or 0)
    quota_limit = int(r.get("quota_limit") or 0)
    remaining = max(0, quota_limit - calls_made)
    pct_used = round(calls_made / quota_limit * 100) if quota_limit else 0

    lines = [
        f"Source {source_id!r} quota: {calls_made}/{quota_limit} calls used ({pct_used}%)",
        f"  remaining={remaining}  window_start={r.get('window_start', '?')}",
    ]
    if remaining == 0:
        lines.append("  🚫 Quota exhausted — no calls available this window.")
    elif remaining <= 2:
        lines.append("  ⚠ Nearly exhausted — allocate remaining calls to highest-priority entities only.")
    elif pct_used < 50:
        lines.append("  ✓ Quota healthy — routine scheduling is fine.")
    return "\n".join(lines)
