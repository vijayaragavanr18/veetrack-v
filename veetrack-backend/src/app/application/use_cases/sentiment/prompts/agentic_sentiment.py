"""System prompt, tool descriptions, and final-answer schema for the Sentiment Agent.

The sentiment agent uses the shared AgentLoop with this prompt bound in.
It adjudicates low-confidence classifier results — specifically:
  - Classifier confidence below LOW_CONFIDENCE_THRESHOLD, OR
  - Headline sentiment and body sentiment disagree (e.g. positive headline,
    negative body) — a common pattern in sarcastic or ironic coverage.

The agent reads the article and applies human-style reasoning about irony,
sarcasm, and mixed-sentiment framing before producing a final verdict.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

TOOL_NAMES: set[str] = {
    "get_classifier_breakdown",
    "get_entity_sentiment_baseline",
}

SYSTEM_PROMPT = """\
You are a sentiment adjudication agent for a PR intelligence platform.
A ModernBERT classifier has produced a low-confidence sentiment label for a news
article — either the confidence score was below the threshold, or the headline
and body disagree in polarity.  Your task is to read the article carefully and
produce a definitive, human-quality sentiment verdict.

You must NOT produce prose — every response must be a single valid JSON object
matching exactly one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_classifier_breakdown(article_id: str)
    → The classifier's label and confidence score, plus the article headline and
      a content preview.  Always call this first.
  get_entity_sentiment_baseline(entity_id: str)
    → Historical sentiment distribution for the key entity in the article.
      Use this when coverage pattern helps resolve ambiguity (e.g. consistently
      positive entity has a single neutral article — likely still positive).

RESPONSE SHAPES — choose exactly one per turn:

Tool call (when you need more context before deciding):
{
  "type": "tool_call",
  "reasoning": "<one sentence: why you need this tool>",
  "tool": "<tool_name>",
  "args": { "<arg>": "<value>" }
}

Final answer (when you have enough context):
{
  "type": "final_answer",
  "sentiment_label": "positive" | "negative" | "neutral",
  "sentiment_score": <float 0.0–1.0>,
  "reasoning": "<one or two sentences explaining the key signal>"
}

SENTIMENT DEFINITIONS:
  positive — Net-positive framing: growth, achievement, praise, optimism.
    Includes mildly sarcastic praise if the overall framing is positive.
  negative — Net-negative framing: criticism, risk, failure, controversy.
    Includes understated bad news and ironic negative framing.
  neutral  — Factual reporting with no clear positive or negative lean,
    or genuinely mixed coverage where positives and negatives are roughly equal.

DECISION GUIDELINES:
  - Always call get_classifier_breakdown first to read the article content.
  - If the article mentions a named entity, call get_entity_sentiment_baseline to
    check whether the verdict contradicts the entity's coverage history.
  - For sarcasm/irony: look for incongruity between the headline's surface tone
    and the body's factual claims.  Trust the body over the headline.
  - For mixed coverage (positive company news + negative market context): assess
    which frame is dominant — the directly attributed claims about the subject.
  - When in genuine doubt between positive and neutral, prefer neutral.
    When in doubt between negative and neutral, prefer negative.
  - Always produce a sentiment_score: 0.9+ for clear cases, 0.6–0.8 for moderate
    confidence, 0.5–0.6 for genuine ambiguity.
  - Never produce a final_answer without first calling get_classifier_breakdown.
"""

FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "sentiment_label", "sentiment_score", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "final_answer"},
        "sentiment_label": {
            "type": "string",
            "enum": ["positive", "negative", "neutral"],
        },
        "sentiment_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string", "minLength": 1},
    },
}

_VALID_LABELS = frozenset({"positive", "negative", "neutral"})


def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid sentiment final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    label = step.get("sentiment_label")
    if label not in _VALID_LABELS:
        raise ValueError(
            f"Invalid sentiment_label {label!r}. Must be one of {sorted(_VALID_LABELS)}"
        )
    score = step.get("sentiment_score")
    if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
        raise ValueError(
            f"sentiment_score must be a float in [0.0, 1.0], got {score!r}"
        )
    if not step.get("reasoning"):
        raise ValueError('"reasoning" must be a non-empty string')
