"""Tool: get_entity_event_history.

Returns past distinct events for this entity.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

async def get_entity_event_history(args: dict[str, Any], db_query: DbQuery) -> str:
    entity_id = str(args.get("entity_id", ""))
    
    rows = await db_query(
        """
        SELECT id, title, created_at
        FROM stories
        WHERE primary_entity_id = :eid
        ORDER BY created_at DESC
        LIMIT 10
        """,
        {"eid": entity_id},
    )
    
    if not rows:
        return f"No past events found for entity {entity_id!r}."
        
    lines = [f"Past events for entity {entity_id!r}:"]
    for r in rows:
        lines.append(f"  - [{r['id']}] {r['title']} ({r['created_at']})")
        
    return "\n".join(lines)
