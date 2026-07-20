"""Versioned prompt templates for the executive summary agent.

Version history:
  v1 — initial prompt; structured JSON output for what_happened / why_happened.
"""

from __future__ import annotations

from dataclasses import dataclass

PROMPT_VERSION = "v1"

_SYSTEM = """\
You are an AI analyst writing concise executive summaries for a media intelligence platform.
Your audience is PR and executive teams who need to act quickly.
Write clearly, factually, and without editorial bias.
"""

_USER_TEMPLATE = """\
Story title: {title}

Articles ({article_count}):
{article_summaries}

Key entities: {entities}

Write an executive summary with exactly two sections:
1. what_happened — 2-3 sentences describing the core event/development
2. why_happened  — 2-3 sentences explaining the context, cause, or significance

Return ONLY a JSON object with keys "what_happened" and "why_happened".
"""

RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "what_happened": {"type": "string"},
        "why_happened": {"type": "string"},
    },
    "required": ["what_happened", "why_happened"],
    "additionalProperties": False,
}


@dataclass
class ArticleSummary:
    headline: str
    published_at: str
    content_snippet: str  # first ~300 chars of clean_content


def build_prompt(
    title: str,
    articles: list[ArticleSummary],
    entity_names: list[str],
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the executive summary request."""
    summaries = "\n".join(
        f"- [{a.published_at}] {a.headline}: {a.content_snippet[:300]}"
        for a in articles
    )
    entities_str = ", ".join(entity_names) if entity_names else "none identified"
    user = _USER_TEMPLATE.format(
        title=title,
        article_count=len(articles),
        article_summaries=summaries,
        entities=entities_str,
    )
    return _SYSTEM, user
