"""Tool: get_watchlist_preferences.

Returns the user's configured sensitivity and channel preferences for a
given watchlist, so the agent knows whether the user wants high-sensitivity
alerts or has restricted hours.

Read-only — never modifies a watchlist.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_watchlist_preferences(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return channel/sensitivity preferences for *watchlist_id*.

    Args dict keys:
        watchlist_id (str): The watchlist to inspect.
    """
    watchlist_id = str(args.get("watchlist_id", ""))

    rows = await db_query(
        """
        SELECT id, entity_id, alert_channels_json,
               sensitivity, quiet_hours_start, quiet_hours_end
        FROM watchlists
        WHERE id = :wid
        LIMIT 1
        """,
        {"wid": watchlist_id},
    )

    if not rows:
        return f"Watchlist {watchlist_id!r} not found."

    r = rows[0]
    channels = r.get("alert_channels_json") or {}
    enabled = [ch for ch, on in (channels.items() if isinstance(channels, dict) else []) if on]
    sensitivity = r.get("sensitivity") or "normal"
    qh_start = r.get("quiet_hours_start")
    qh_end = r.get("quiet_hours_end")

    parts = [
        f"Watchlist {watchlist_id!r}: entity={r.get('entity_id','?')}",
        f"  channels_enabled={enabled}",
        f"  sensitivity={sensitivity}",
    ]
    if qh_start is not None and qh_end is not None:
        parts.append(f"  quiet_hours={qh_start}-{qh_end} UTC")
    return "\n".join(parts)
