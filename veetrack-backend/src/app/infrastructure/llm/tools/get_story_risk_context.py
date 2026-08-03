"""Tool: get_story_risk_context.

Returns the story's current risk level, the confidence score of the latest
recommendation, and whether this update is a new story or a continuation of
an already-alerted cluster.

Read-only.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_story_risk_context(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return risk metadata for *story_id*.

    Args dict keys:
        story_id (str): The story to inspect.
    """
    story_id = str(args.get("story_id", ""))

    # Story basics
    story_rows = await db_query(
        """
        SELECT s.id, s.title, s.risk_level, s.status, s.created_at, s.updated_at,
               e.canonical_name AS entity_name
        FROM stories s
        JOIN entities e ON e.id = s.primary_entity_id
        WHERE s.id = :sid
        LIMIT 1
        """,
        {"sid": story_id},
    )
    if not story_rows:
        return f"Story {story_id!r} not found."

    st = story_rows[0]

    # Latest recommendation confidence
    rec_rows = await db_query(
        """
        SELECT confidence_score, needs_human_review, agent_mode
        FROM story_recommendations
        WHERE story_id = :sid
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        {"sid": story_id},
    )

    # Whether this entity has had a prior alert for a different story
    prior_rows = await db_query(
        """
        SELECT COUNT(*) AS cnt
        FROM alerts a
        JOIN watchlists w ON w.id = a.watchlist_id
        JOIN stories s ON s.id = a.story_id
        WHERE s.primary_entity_id = (
            SELECT primary_entity_id FROM stories WHERE id = :sid
        )
          AND a.story_id != :sid
        """,
        {"sid": story_id},
    )
    prior_alerts = int((prior_rows[0].get("cnt") or 0) if prior_rows else 0)

    lines = [
        f"Story {story_id!r} ({st.get('title','?')!r})",
        f"  risk_level={st.get('risk_level','?')}  status={st.get('status','?')}",
        f"  entity={st.get('entity_name','?')}",
        f"  prior_alerts_for_entity={prior_alerts}",
    ]

    if rec_rows:
        r = rec_rows[0]
        lines.append(
            f"  latest_rec: confidence={r.get('confidence_score','?')} "
            f"needs_human_review={r.get('needs_human_review','?')} "
            f"agent_mode={r.get('agent_mode','?')}"
        )
    else:
        lines.append("  latest_rec: none yet")

    return "\n".join(lines)
