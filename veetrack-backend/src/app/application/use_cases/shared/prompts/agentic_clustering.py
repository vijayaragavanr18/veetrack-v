"""System prompt, tool descriptions, and final-answer schema for the Agentic Clustering & Timeline Agent."""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

TOOL_NAMES: set[str] = {
    "get_cluster_candidate_articles",
    "get_entity_event_history",
}

SYSTEM_PROMPT = """\
You are an expert PR intelligence agent.
Your task is to reconcile borderline clusters of articles and produce a narrative timeline.
HDBSCAN has flagged two stories/clusters as a borderline merge or split candidate.
You must read the actual article content to determine if they are the SAME event (merge)
or DIFFERENT events (keep_separate/split).

You must NOT produce prose — every response must be a single valid JSON object
matching exactly one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_cluster_candidate_articles(cluster_id_a: str, cluster_id_b: str)
    → Full content preview of articles in both candidate clusters.
  get_entity_event_history(entity_id: str)
    → Past distinct events for the entity, to help judge if this is a continuation or a new event.

RESPONSE SHAPES:

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
  "action": "merge" | "split" | "keep_separate",
  "is_pattern": true | false,
  "timeline_highlights": ["<article_id>: <why this is a turning point>"],
  "reasoning": "<summary of why you chose this action>"
}

DECISION GUIDELINES:
  - If the articles describe the same evolving story or event, action="merge".
  - If the articles describe distinct events, action="keep_separate" (or "split").
  - Identify real turning points in the narrative for timeline_highlights (e.g. announcement, investigation, resolution).
"""

_VALID_ACTIONS = frozenset({"merge", "split", "keep_separate"})


def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid clustering final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    action = step.get("action")
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid action {action!r}. Must be one of {sorted(_VALID_ACTIONS)}")
    if not isinstance(step.get("timeline_highlights"), list):
        raise ValueError('"timeline_highlights" must be a list of strings')
    if not isinstance(step.get("is_pattern"), bool):
        raise ValueError('"is_pattern" must be a boolean')
    if not step.get("reasoning") or not isinstance(step.get("reasoning"), str):
        raise ValueError('"reasoning" must be a non-empty string')
