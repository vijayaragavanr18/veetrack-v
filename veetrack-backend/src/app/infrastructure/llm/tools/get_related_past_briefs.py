"""Tool: get_related_past_briefs.

Returns the entity's most recent past executive briefs (story insights).
"""
from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

async def get_related_past_briefs(args: dict[str, Any], db_query: DbQuery) -> str:
    entity_id = str(args.get("entity_id", ""))
    if not entity_id:
        return "Missing entity_id"
    try:
        limit = int(args.get("limit", 3))
    except ValueError:
        limit = 3
        
    rows = await db_query(
        """
        SELECT s.title, si.what_happened, si.why_happened, s.created_at
        FROM story_insights si
        JOIN stories s ON si.story_id = s.id
        WHERE s.primary_entity_id = :eid
        ORDER BY s.created_at DESC
        LIMIT :limit
        """,
        {"eid": entity_id, "limit": limit}
    )
    
    if not rows:
        return f"No past briefs found for entity {entity_id}."
        
    lines = [f"Recent briefs for entity {entity_id}:"]
    for r in rows:
        lines.append(f"Story: {r['title']} ({r['created_at']})")
        lines.append(f"  What: {r['what_happened']}")
        lines.append(f"  Why: {r['why_happened']}")
    return "\n".join(lines)
