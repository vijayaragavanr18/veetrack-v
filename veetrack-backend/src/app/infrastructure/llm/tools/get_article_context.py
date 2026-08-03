"""Tool: get_article_context.

Returns the surrounding sentence(s) around a named-entity mention within an
article.  The agent uses this to disambiguate ambiguous mentions — "Apple"
near "CEO" signals a company context; near "orchard" signals something else.

Read-only.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

DbQuery = Callable[[str, dict[str, Any]], Awaitable[list[dict[str, Any]]]]

# Characters of surrounding context to return on each side of the mention.
_CONTEXT_WINDOW_CHARS = 300


def _extract_context(
    text: str,
    mention_offset: int,
    window: int = _CONTEXT_WINDOW_CHARS,
) -> str:
    """Return up to *window* characters either side of *mention_offset*."""
    if not text:
        return ""
    start = max(0, mention_offset - window)
    end = min(len(text), mention_offset + window)
    snippet = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


async def get_article_context(
    args: dict[str, Any],
    db_query: DbQuery,
) -> str:
    """Return context around a mention for disambiguation.

    Args dict keys:
        article_id     (str): The article containing the mention.
        mention_offset (int): Character offset of the mention start in clean_content.
                              Defaults to 0 (use headline context only) if omitted.
    """
    article_id = str(args.get("article_id", ""))
    mention_offset = max(0, int(args.get("mention_offset", 0)))

    rows = await db_query(
        """
        SELECT headline, clean_content
        FROM articles
        WHERE id = :aid
        LIMIT 1
        """,
        {"aid": article_id},
    )

    if not rows:
        return f"No article found for id {article_id!r}."

    r = rows[0]
    headline = str(r.get("headline") or "")
    content = str(r.get("clean_content") or "")

    lines = [
        f"Article {article_id!r}:",
        f"  headline: {headline!r}",
    ]

    if content:
        context = _extract_context(content, mention_offset)
        lines.append(f"  context (±{_CONTEXT_WINDOW_CHARS} chars around offset {mention_offset}):")
        lines.append(f"    {context!r}")
    else:
        lines.append("  (no clean_content available — use headline for context)")

    return "\n".join(lines)
