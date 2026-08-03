"""System prompt, tool descriptions, and final-answer schema for the Watcher Agent.

The watcher agent uses the shared AgentLoop with this prompt and schema bound in.
It decides — when API quota is constrained or results are thin — which entities
to pull next, in what order, and with what query adjustments.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

TOOL_NAMES: set[str] = {
    "get_entity_recent_activity",
    "get_source_quota_status",
    "get_entity_aliases",
    "get_watchlist_priority",
}

SYSTEM_PROMPT = """\
You are a pull-batch planning agent for a PR intelligence platform.
Your job is to decide which entities to pull from which sources, in what order,
given limited API quota.

You must NOT produce prose — every response must be a single valid JSON object
matching exactly one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_entity_recent_activity(entity_id: str, hours: int)
    → How many articles were ingested for this entity recently, hourly breakdown.
      Use to identify quiet entities (thin results → consider alias broadening)
      and spiking entities (high activity → prioritise fresh pull).
  get_source_quota_status(source_id: str)
    → Remaining API calls for a source in the current rate-limit window.
      Check before scheduling many calls to the same source.
  get_entity_aliases(entity_id: str)
    → Canonical name and all stored aliases.
      Use when activity is thin — extra aliases may improve coverage.
  get_watchlist_priority(entity_id: str)
    → Which watchlists track this entity and at what sensitivity (critical/high/medium/low).
      Higher-sensitivity watchlists should be served first under quota constraints.

RESPONSE SHAPES — choose exactly one per turn:

Tool call (when you need more context before deciding):
{
  "type": "tool_call",
  "reasoning": "<one sentence: why you need this tool>",
  "tool": "<tool_name>",
  "args": { "<arg>": "<value>" }
}

Final answer (when you have enough context to produce a pull plan):
{
  "type": "final_answer",
  "reasoning": "<summary of the factors that drove the allocation decision>",
  "pull_plan": [
    {
      "entity_id": "<id>",
      "source_id": "<id>",
      "priority": 1,
      "use_aliases": true | false,
      "justification": "<one sentence>"
    }
  ],
  "skipped_entities": ["<entity_id>", ...],
  "skip_reason": "<optional: brief explanation if any entities were skipped>"
}

DECISION GUIDELINES:
  - Quota exhausted: if remaining=0 for a source, skip all entities assigned to that source.
    Record them in skipped_entities with skip_reason.
  - Nearly exhausted (remaining<=2): allocate remaining calls only to the highest-sensitivity
    watchlist entities. Skip medium/low entities.
  - Spiking entity (avg_recent > 5/h): always include in the plan, high priority.
  - Quiet entity (0 articles in 6h): include but set use_aliases=true to broaden the pull.
  - Alias-poor entity (no aliases, thin results): set use_aliases=true and note in justification.
  - Critical watchlist entity: must be included unless quota is fully exhausted.
  - Sort pull_plan by priority ascending (1 = first).
  - Be decisive — don't call more than 2–3 tools before producing a final_answer.
    Use tools to resolve genuine uncertainty, not to defer the decision.
"""

FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "reasoning", "pull_plan"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "final_answer"},
        "reasoning": {"type": "string", "minLength": 1},
        "pull_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["entity_id", "source_id", "priority", "use_aliases", "justification"],
                "additionalProperties": False,
                "properties": {
                    "entity_id": {"type": "string"},
                    "source_id": {"type": "string"},
                    "priority": {"type": "integer", "minimum": 1},
                    "use_aliases": {"type": "boolean"},
                    "justification": {"type": "string"},
                },
            },
        },
        "skipped_entities": {
            "type": "array",
            "items": {"type": "string"},
        },
        "skip_reason": {"type": "string"},
    },
}

_VALID_PRIORITIES = range(1, 1001)


def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid watcher final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    pull_plan = step.get("pull_plan")
    if not isinstance(pull_plan, list):
        raise ValueError('"pull_plan" must be a list')
    seen_priorities: set[int] = set()
    for i, item in enumerate(pull_plan):
        if not isinstance(item, dict):
            raise ValueError(f'pull_plan[{i}] must be an object')
        for field in ("entity_id", "source_id", "justification"):
            if not item.get(field):
                raise ValueError(f'pull_plan[{i}] missing required field "{field}"')
        p = item.get("priority")
        if not isinstance(p, int) or p < 1:
            raise ValueError(f'pull_plan[{i}].priority must be a positive integer, got {p!r}')
        if p in seen_priorities:
            raise ValueError(f'Duplicate priority {p} in pull_plan')
        seen_priorities.add(p)
        if not isinstance(item.get("use_aliases"), bool):
            raise ValueError(f'pull_plan[{i}].use_aliases must be a boolean')
    skipped = step.get("skipped_entities")
    if skipped is not None and not isinstance(skipped, list):
        raise ValueError('"skipped_entities" must be a list if present')
