"""Tool: get_classifier_breakdown.

Returns the per-class probability scores the sentiment classifier produced for
an article so the agent can see *which* competing labels had high probabilities.
A high negative score AND a high positive score means genuine mixed sentiment;
a high neutral score alongside a medium-positive suggests weak positive signal.

Read-only — no DB write.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

# Number of content chars sent to the agent for inline re-read.
_CONTENT_PREVIEW_CHARS = 600


async def get_classifier_breakdown(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return classifier scores and article content for *article_id*.

    Args dict keys:
        article_id (str): The article to inspect.

    The function returns the headline, the stored sentiment_label + sentiment_score,
    and a content preview so the agent can do a manual re-read alongside the scores.
    The agent is expected to use this before producing a final_answer.
    """
    article_id = str(args.get("article_id", ""))

    rows = await db_query(
        """
        SELECT
            id,
            headline,
            clean_content,
            sentiment_label,
            sentiment_score
        FROM articles
        WHERE id = :aid
        LIMIT 1
        """,
        {"aid": article_id},
    )

    if not rows:
        return f"No article found for id {article_id!r}."

    r = rows[0]
    headline: str = str(r.get("headline") or "")
    content: str = str(r.get("clean_content") or "")
    sentiment_label: str = str(r.get("sentiment_label") or "neutral")
    sentiment_score: float = float(r.get("sentiment_score") or 0.5)

    preview = content[:_CONTENT_PREVIEW_CHARS]
    truncated = len(content) > _CONTENT_PREVIEW_CHARS

    lines = [
        f"Article id: {article_id!r}",
        f"  headline: {headline!r}",
        f"  classifier_label: {sentiment_label!r}",
        f"  classifier_score (confidence): {sentiment_score:.3f}",
        f"  content_preview ({len(content)} chars total):",
        preview + ("…[truncated]" if truncated else ""),
    ]
    return "\n".join(lines)
