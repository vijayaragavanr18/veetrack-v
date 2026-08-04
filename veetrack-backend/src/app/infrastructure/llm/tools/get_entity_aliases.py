"""Tool: get_entity_aliases.

Returns canonical name + all known aliases for an entity so the agent can
broaden search queries when recent activity looks unexpectedly thin.

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]


async def get_entity_aliases(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return the canonical name and all stored aliases for *entity_id*.

    Args dict keys:
        entity_id (str): The entity to look up.
    """
    entity_id = str(args.get("entity_id", ""))

    entity_rows = await db_query(
        """
        SELECT canonical_name, entity_type
        FROM entities
        WHERE id = :eid
        LIMIT 1
        """,
        {"eid": entity_id},
    )

    if not entity_rows:
        return f"No entity found for id {entity_id!r}."

    canonical_name = entity_rows[0].get("canonical_name", "")
    entity_type = entity_rows[0].get("entity_type", "unknown")

    alias_rows = await db_query(
        """
        SELECT alias
        FROM entity_aliases
        WHERE entity_id = :eid
        ORDER BY alias
        """,
        {"eid": entity_id},
    )

    aliases = [str(r.get("alias", "")) for r in alias_rows if r.get("alias")]

    lines = [
        f"Entity {entity_id!r} ({entity_type}): canonical_name={canonical_name!r}",
        f"  alias_count={len(aliases)}",
    ]
    if aliases:
        alias_list = ", ".join(f"{a!r}" for a in aliases[:10])
        lines.append(f"  aliases=[{alias_list}]")
        if len(aliases) > 10:
            lines.append(f"  … and {len(aliases) - 10} more.")
    else:
        lines.append(
            "  No aliases stored — if activity is thin, consider adding aliases "
            "to broaden future pull queries."
        )
    return "\n".join(lines)
