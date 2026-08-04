"""Tool: get_candidate_duplicate.

Fetches the content of the near-match article so the agent can do a
side-by-side comparison and decide whether the new article is a true
duplicate, a wire update, or a distinct follow-up.

Read-only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

_CONTENT_PREVIEW_CHARS = 800


async def get_candidate_duplicate(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return key fields from the candidate duplicate article *article_id*.

    Args dict keys:
        article_id (str): The existing article to compare against.
    """
    article_id = str(args.get("article_id", ""))

    rows = await db_query(
        """
        SELECT
            id,
            headline,
            publisher,
            published_at,
            clean_content,
            is_duplicate_of
        FROM articles
        WHERE id = :aid
        LIMIT 1
        """,
        {"aid": article_id},
    )

    if not rows:
        return f"No article found for id {article_id!r}."

    r = rows[0]
    content: str = str(r.get("clean_content") or "")
    preview = content[:_CONTENT_PREVIEW_CHARS]
    truncated = len(content) > _CONTENT_PREVIEW_CHARS

    lines = [
        f"Candidate duplicate: id={article_id!r}",
        f"  headline: {r.get('headline', '')!r}",
        f"  publisher: {r.get('publisher', '')!r}",
        f"  published_at: {r.get('published_at', '?')}",
        f"  is_duplicate_of: {r.get('is_duplicate_of')}",
        f"  content_preview ({len(content)} chars total):",
        preview + ("…[truncated]" if truncated else ""),
    ]
    return "\n".join(lines)
