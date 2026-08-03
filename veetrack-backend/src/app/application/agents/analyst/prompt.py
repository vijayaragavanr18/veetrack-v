"""System prompt and schema validation for the Analyst Agent.

The Analyst Agent replaces basic Named Entity Recognition (NER). It reads an accepted
article and builds a structured Knowledge Graph of facts, extracting complex
relationships (Subject -> Predicate -> Object) and sentiment drivers.
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "1.0"

# Note: The Analyst is a single-step extractor, it usually doesn't need to loop with tools
# unless it needs to look up canonical entity names, but for now we do direct extraction.
TOOL_NAMES: set[str] = set()

SYSTEM_PROMPT = """\
You are an Analyst Agent for a PR intelligence platform. Your job is to read news articles
or social media posts and extract a structured Knowledge Graph.

Basic entity extractors just find names (e.g., "Apple"). Your job is to understand
the relationships and business implications.

You must NOT produce prose — every response must be a single valid JSON object
matching the exact shape below.

RESPONSE SHAPE:
{
  "type": "final_answer",
  "knowledge_graph": [
    {
      "subject": "<Entity (e.g., Apple)>",
      "predicate": "<Action/Relationship (e.g., acquired)>",
      "object": "<Target (e.g., AI Startup)>",
      "context": "<Why this matters>"
    }
  ],
  "sentiment_drivers": [
    {
      "entity": "<Entity name>",
      "driver": "<What is causing the sentiment>",
      "sentiment": "positive" | "negative" | "neutral"
    }
  ]
}

EXTRACTION GUIDELINES:
  - Focus on business-critical relationships: acquisitions, lawsuits, product launches, executive changes, regulatory actions.
  - Do NOT extract trivial relationships (e.g., "Reporter writes for NYT").
  - The `sentiment_drivers` array should clearly state *why* an entity looks good or bad in this text.
"""

def validate_final_answer(step: dict[str, Any]) -> None:
    """Raise ValueError if *step* is not a valid analyst final_answer."""
    if step.get("type") != "final_answer":
        raise ValueError('Expected type="final_answer"')
    
    kg = step.get("knowledge_graph")
    if not isinstance(kg, list):
        raise ValueError('"knowledge_graph" must be a list')
    
    for i, edge in enumerate(kg):
        if not isinstance(edge, dict):
            raise ValueError(f'knowledge_graph[{i}] must be an object')
        for field in ("subject", "predicate", "object", "context"):
            if field not in edge:
                raise ValueError(f'knowledge_graph[{i}] missing required field "{field}"')

    sd = step.get("sentiment_drivers")
    if not isinstance(sd, list):
        raise ValueError('"sentiment_drivers" must be a list')
        
    for i, driver in enumerate(sd):
        if not isinstance(driver, dict):
            raise ValueError(f'sentiment_drivers[{i}] must be an object')
        for field in ("entity", "driver", "sentiment"):
            if field not in driver:
                raise ValueError(f'sentiment_drivers[{i}] missing required field "{field}"')
        if driver.get("sentiment") not in ("positive", "negative", "neutral"):
             raise ValueError(f'sentiment_drivers[{i}].sentiment must be positive/negative/neutral')
