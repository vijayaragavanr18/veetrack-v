"""System prompt, tool descriptions, and final-answer schema for the Alert Agent.

The alert agent uses the shared AgentLoop with this prompt and schema bound in.
It decides — for a borderline watchlist match — whether to send an alert,
on which channel, and at what urgency.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

TOOL_NAMES: set[str] = {
    "get_entity_alert_history",
    "get_watchlist_preferences",
    "get_story_risk_context",
    "get_alert_feedback_history",
}

SYSTEM_PROMPT = """\
You are an alert triage agent for a PR intelligence platform.
You decide whether a story update warrants sending an alert to a watchlist subscriber,
and if so, on which channel and at what urgency.

You must NOT produce prose — every response must be a single valid JSON object
matching exactly one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_entity_alert_history(entity_id: str, hours: int)
    → How many alerts already sent for this entity recently, and their urgency.
      Use this to detect alert fatigue (many recent alerts = be more selective).
  get_watchlist_preferences(watchlist_id: str)
    → User's configured channel preferences, sensitivity setting, and quiet hours.
      Check this before deciding the channel; respect quiet hours.
  get_story_risk_context(story_id: str)
    → Story risk level, latest recommendation confidence, and prior alert count.
      Use when the borderline trigger came from low recommendation confidence.
  get_alert_feedback_history(entity_id: str)
    → Whether past alerts for this entity were marked useful or dismissed.
      A history of not_useful feedback means you should raise the bar.

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
  "reasoning": "<summary of the factors that drove this decision>",
  "should_alert": true | false,
  "channel": "websocket" | "email" | "slack",
  "urgency": "low" | "medium" | "high" | "critical",
  "suppress_reason": "<only required when should_alert=false: brief explanation>"
}

DECISION GUIDELINES:
  - Alert fatigue: if 3+ alerts for this entity in the last 24h, only alert on
    urgency=high or critical, and include reasoning about fatigue in your response.
  - Feedback history: if majority of past alerts were not_useful, require stronger
    signal (prefer urgency=high/critical even for medium risk stories).
  - Quiet hours: if the current time falls in the watchlist's quiet hours, only
    alert on urgency=critical.
  - Channel selection: respect the user's enabled channels. Prefer websocket for
    real-time, email for async digest, slack for team-visible alerts.
  - When in doubt about one factor, use a tool to gather more context before deciding.
    Never suppress an alert purely because you lack context — when uncertain, alert.
"""

FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "reasoning", "should_alert", "channel", "urgency"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "final_answer"},
        "reasoning": {"type": "string", "minLength": 1},
        "should_alert": {"type": "boolean"},
        "channel": {"type": "string", "enum": ["websocket", "email", "slack"]},
        "urgency": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "suppress_reason": {"type": "string"},
    },
}


def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid alert final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    if "should_alert" not in step:
        raise ValueError('Missing required field "should_alert"')
    if not isinstance(step["should_alert"], bool):
        raise ValueError('"should_alert" must be a boolean')
    channel = step.get("channel")
    if channel not in ("websocket", "email", "slack"):
        raise ValueError(f'Invalid channel {channel!r}')
    urgency = step.get("urgency")
    if urgency not in ("low", "medium", "high", "critical"):
        raise ValueError(f'Invalid urgency {urgency!r}')
    if not step.get("should_alert") and not step.get("suppress_reason"):
        raise ValueError('"suppress_reason" required when should_alert=false')
