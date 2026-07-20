"""Versioned prompt templates for the recommendation agent.

Version history:
  v1 — initial prompt; explicitly elicits structured confidence self-assessment
       (not a free-text guess). Three audience-specific actions returned in one call.
"""

from __future__ import annotations

from dataclasses import dataclass

PROMPT_VERSION = "v1"

_SYSTEM = """\
You are an AI advisor generating actionable recommendations for PR and executive teams.
Your output must be structured, actionable, and cautious.

IMPORTANT: You must perform an honest self-assessment of your confidence.
- High confidence (0.80–1.00): You have strong, unambiguous signals from the articles.
- Medium confidence (0.50–0.79): Some signals are mixed or the situation is evolving.
- Low confidence (0.00–0.49): Insufficient evidence; recommend human review.

Never inflate confidence. Underconfident recommendations are safer than overconfident ones.
"""

_USER_TEMPLATE = """\
Story: {title}

Executive summary:
What happened: {what_happened}
Why it happened: {why_happened}

Articles ({article_count} total). Most recent headlines:
{headlines}

Key entities: {entities}

Generate three separate recommendations — one per audience: pr, exec, marketing.
For each recommendation:
  1. Write a concise, actionable recommendation (2-3 sentences).
  2. Assign a risk_level: one of "low", "medium", "high", "critical".
  3. Assign a confidence_score: 0.0–1.0 reflecting how certain you are this is the right action.
  4. Justify your confidence_score in one sentence (confidence_rationale).

Return ONLY a JSON object with this exact schema.
"""

RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "pr": {
            "type": "object",
            "properties": {
                "recommendation_text": {"type": "string"},
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence_rationale": {"type": "string"},
            },
            "required": [
                "recommendation_text",
                "risk_level",
                "confidence_score",
                "confidence_rationale",
            ],
        },
        "exec": {
            "type": "object",
            "properties": {
                "recommendation_text": {"type": "string"},
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence_rationale": {"type": "string"},
            },
            "required": [
                "recommendation_text",
                "risk_level",
                "confidence_score",
                "confidence_rationale",
            ],
        },
        "marketing": {
            "type": "object",
            "properties": {
                "recommendation_text": {"type": "string"},
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence_rationale": {"type": "string"},
            },
            "required": [
                "recommendation_text",
                "risk_level",
                "confidence_score",
                "confidence_rationale",
            ],
        },
    },
    "required": ["pr", "exec", "marketing"],
    "additionalProperties": False,
}


@dataclass
class RecommendationPromptContext:
    title: str
    what_happened: str
    why_happened: str
    article_count: int
    recent_headlines: list[str]
    entity_names: list[str]


def build_prompt(ctx: RecommendationPromptContext) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the recommendation request."""
    headlines_str = "\n".join(f"- {h}" for h in ctx.recent_headlines[:8])
    entities_str = ", ".join(ctx.entity_names) if ctx.entity_names else "none identified"
    user = _USER_TEMPLATE.format(
        title=ctx.title,
        what_happened=ctx.what_happened or "(not yet generated)",
        why_happened=ctx.why_happened or "(not yet generated)",
        article_count=ctx.article_count,
        headlines=headlines_str,
        entities=entities_str,
    )
    return _SYSTEM, user
