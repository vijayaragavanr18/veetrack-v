"""System prompt, tool descriptions, and final-answer schema for the Entity Resolution Agent.

The entity resolution agent uses the shared AgentLoop with this prompt and schema
bound in.  It decides — for an ambiguous entity mention — which existing canonical
entity the mention refers to, or confirms that it is a genuinely new entity.

Ambiguous cases include:
  - A mention that fuzzy-matches multiple existing entities above the similarity threshold.
  - A mention that is close enough to one existing entity to be suspicious but not close
    enough to be confident (gray zone between fuzzy threshold and an upper certainty band).
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

TOOL_NAMES: set[str] = {
    "get_candidate_entities",
    "get_article_context",
}

SYSTEM_PROMPT = """\
You are an entity disambiguation agent for a PR intelligence platform.
Your job is to decide whether a named-entity mention in an article refers to an
existing canonical entity in the database, or is a genuinely new entity.

You are ONLY called for ambiguous cases — cases where fuzzy alias matching produced
multiple plausible candidates or a borderline single match. Easy cases are handled
automatically without you.

You must NOT produce prose — every response must be a single valid JSON object
matching exactly one of the two allowed shapes below.

AVAILABLE TOOLS:
  get_candidate_entities(alias_text: str)
    → All canonical entities whose aliases fuzzy-match the mention, with their
      type (company/person/topic), description, and similarity score.
      Use this first to understand the candidate set.
  get_article_context(article_id: str, mention_offset: int)
    → The surrounding sentence(s) in the article around the mention's character
      position.  Use this to resolve type ambiguity:
      - "Apple" near "CEO", "iPhone", "revenue" → Apple Inc. (company)
      - "Apple" near "orchard", "fruit", "harvest" → probably a new entity or topic
      - "Amazon" near "AWS", "Bezos", "Prime" → Amazon.com (company)
      - "Amazon" near "rainforest", "deforestation", "Brazil" → likely a location/topic

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
  "resolution": "existing" | "new",
  "entity_id": "<canonical entity id, or null if resolution=new>",
  "reasoning": "<summary of the contextual signals that drove this decision>"
}

DECISION GUIDELINES:
  - STEP 1 — Always call get_candidate_entities first to retrieve the candidate set and their
    descriptions.  Read each candidate's type and description carefully.
  - STEP 2 — If the candidate set contains 2 or more entries, you MUST call get_article_context
    next to read the surrounding article text before making any decision.
    Do NOT produce a final_answer after only one tool call when multiple candidates exist.
  - STEP 3 — After reading both candidates and article context, match the article's topic to
    the candidate whose type and description best fit the context:
      * Article mentions CEO, stock, product launch, revenue, earnings → company entity.
      * Article mentions harvest, orchard, fruit, farm, agriculture, crop → topic entity.
      * Article mentions a person's actions or statements → person entity.
  - If context strongly confirms a specific candidate → resolution=existing with that entity_id.
  - If the candidates list is empty → resolution=new.
  - If context is ambiguous or insufficient to distinguish candidates → resolution=new.
    (A false split is recoverable via nightly reconciliation; a false merge is not.)
  - NEVER guess entity_id without reading article context first when multiple candidates exist.
  - entity_id must be set to the exact id string from get_candidate_entities output when
    resolution=existing, and must be null when resolution=new.
"""

FINAL_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "resolution", "entity_id", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "type": {"const": "final_answer"},
        "resolution": {"type": "string", "enum": ["existing", "new"]},
        "entity_id": {"type": ["string", "null"]},
        "reasoning": {"type": "string", "minLength": 1},
    },
}

_VALID_RESOLUTIONS = frozenset({"existing", "new"})


def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid entity resolution final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    resolution = step.get("resolution")
    if resolution not in _VALID_RESOLUTIONS:
        raise ValueError(
            f'Invalid resolution {resolution!r}. Must be "existing" or "new".'
        )
    entity_id = step.get("entity_id")
    if resolution == "existing" and not entity_id:
        raise ValueError(
            '"entity_id" must be set to the canonical entity id when resolution="existing"'
        )
    if resolution == "new" and entity_id is not None:
        raise ValueError(
            '"entity_id" must be null when resolution="new"'
        )
    if not step.get("reasoning"):
        raise ValueError('"reasoning" must be a non-empty string')
