"""Tool: get_entity_sentiment_baseline.

Returns the historical sentiment distribution for an entity so the agent can
judge whether a low-confidence label is an anomaly or consistent with prior
coverage.

For example, if 90 % of prior articles about an entity were positive and the
current article is labelled neutral with 0.55 confidence, the agent can
reasonably confirm positive — but if prior coverage was evenly split, the
agent should leave the low-confidence label alone.

Read-only — no DB write.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

# Cap lookback to avoid pulling thousands of rows for mature entities.
_MAX_HISTORY_ROWS = 50


async def get_entity_sentiment_baseline(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return aggregated sentiment distribution for *entity_id*.

    Args dict keys:
        entity_id (str): The entity whose sentiment history to retrieve.

    Returns a summary of positive/negative/neutral counts + percentages over
    the most recent _MAX_HISTORY_ROWS articles mentioning the entity,
    plus the entity's canonical name.
    """
    entity_id = str(args.get("entity_id", ""))

    # Fetch entity name
    entity_rows = await db_query(
        "SELECT canonical_name, type FROM entities WHERE id = :eid LIMIT 1",
        {"eid": entity_id},
    )
    if not entity_rows:
        return f"No entity found for id {entity_id!r}."

    canonical_name: str = str(entity_rows[0].get("canonical_name") or "")
    entity_type: str = str(entity_rows[0].get("type") or "")

    # Fetch recent sentiment labels via article_entities join
    sentiment_rows = await db_query(
        f"""
        SELECT a.sentiment_label
        FROM article_entities ae
        JOIN articles a ON a.id = ae.article_id
        WHERE ae.entity_id = :eid
          AND a.sentiment_label IS NOT NULL
        ORDER BY a.published_at DESC
        LIMIT {_MAX_HISTORY_ROWS}
        """,
        {"eid": entity_id},
    )

    if not sentiment_rows:
        return (
            f"Entity {canonical_name!r} ({entity_type}) has no prior sentiment history.\n"
            "No baseline available — treat this article as the first data point."
        )

    counts: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    for row in sentiment_rows:
        label = str(row.get("sentiment_label") or "neutral").lower()
        if label in counts:
            counts[label] += 1
        else:
            counts["neutral"] += 1

    total = sum(counts.values())
    pos_pct = 100 * counts["positive"] // total
    neg_pct = 100 * counts["negative"] // total
    neu_pct = 100 * counts["neutral"] // total
    dominant = max(counts, key=lambda k: counts[k])

    lines = [
        f"Sentiment baseline for entity {canonical_name!r} ({entity_type})",
        f"  sample: {total} recent articles",
        f"  positive: {counts['positive']} ({pos_pct}%)",
        f"  negative: {counts['negative']} ({neg_pct}%)",
        f"  neutral:  {counts['neutral']} ({neu_pct}%)",
        f"  dominant_label: {dominant!r}",
    ]
    return "\n".join(lines)
