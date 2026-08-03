"""Tool: get_entity_background.

Returns a short standing profile of the entity.
"""
from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

async def get_entity_background(args: dict[str, Any], db_query: DbQuery) -> str:
    entity_id = str(args.get("entity_id", ""))
    if not entity_id:
        return "Missing entity_id"
    rows = await db_query("SELECT canonical_name, type, metadata_json FROM entities WHERE id = :eid", {"eid": entity_id})
    if not rows:
        return f"No entity found for id {entity_id!r}"
        
    r = rows[0]
    return f"Entity: {r['canonical_name']} ({r['type']})\nMetadata: {r.get('metadata_json', '{}')}"
