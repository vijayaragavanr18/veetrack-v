"""Tool: get_candidate_entities.

Returns all canonical entities whose aliases fuzzy-match an entity mention,
along with their type and description, so the agent can pick the right one
when the mention is ambiguous.

Read-only.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

# Minimum trigram similarity for a candidate to be worth showing to the agent.
_MIN_CANDIDATE_SIMILARITY = 0.3
# Character 3-gram helpers (mirrors resolve_entity.py, kept local to avoid cross-layer import)


def _trigram_set(text: str) -> set[str]:
    s = text.strip().lower()
    if len(s) < 3:
        return {s}
    return {s[i : i + 3] for i in range(len(s) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    ta, tb = _trigram_set(a), _trigram_set(b)
    if not ta and not tb:
        return 1.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


async def get_candidate_entities(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return all canonical entities whose aliases fuzzy-match *alias_text*.

    Args dict keys:
        alias_text (str): The raw entity mention to look up.
    """
    alias_text = str(args.get("alias_text", "")).strip()
    if not alias_text:
        return "alias_text is required."

    # Fetch all aliases and their canonical entity metadata in one query.
    rows = await db_query(
        """
        SELECT
            ea.alias_text AS alias,
            e.id          AS entity_id,
            e.canonical_name,
            e.type         AS entity_type,
            e.metadata_json ->> 'description' AS description
        FROM entity_aliases ea
        JOIN entities e ON e.id = ea.entity_id
        ORDER BY e.canonical_name, ea.alias_text
        """,
        {},
    )

    # Score and deduplicate by entity_id (keep best alias score per entity).
    scores: dict[str, tuple[float, dict[str, Any]]] = {}
    for r in rows:
        sim = _trigram_similarity(alias_text, str(r.get("alias", "")))
        if sim < _MIN_CANDIDATE_SIMILARITY:
            continue
        eid = str(r.get("entity_id", ""))
        if eid not in scores or sim > scores[eid][0]:
            scores[eid] = (sim, r)

    if not scores:
        return (
            f"No candidate entities found for {alias_text!r} "
            f"(threshold={_MIN_CANDIDATE_SIMILARITY}). "
            "This mention is likely a genuinely new entity."
        )

    # Sort by similarity descending.
    ranked = sorted(scores.values(), key=lambda x: x[0], reverse=True)

    lines = [f"Candidates for {alias_text!r} ({len(ranked)} found):"]
    for sim, r in ranked[:10]:  # cap at 10 for context-window safety
        desc = str(r.get("description") or "no description")
        if len(desc) > 120:
            desc = desc[:120] + "…"
        lines.append(
            f"  - entity_id={r.get('entity_id')!r}  "
            f"canonical={r.get('canonical_name')!r}  "
            f"type={r.get('entity_type')!r}  "
            f"sim={sim:.2f}  "
            f"desc={desc!r}"
        )
    if len(ranked) > 10:
        lines.append(f"  … and {len(ranked) - 10} more candidates omitted.")
    return "\n".join(lines)
