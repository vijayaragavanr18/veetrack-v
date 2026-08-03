"""Use case: The Analyst Agent builds a Knowledge Graph from text."""

from __future__ import annotations

import structlog
from typing import Any

from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

class AnalystAgent:
    """Agent that reads an article and extracts complex business relationships.
    
    This replaces flat Named Entity Recognition (NER) with deep semantic extraction.
    
    Parameters
    ----------
    gateway:
        LLMGateway used to run the agent.
    """

    def __init__(
        self,
        gateway: LLMGateway,
    ) -> None:
        self._gateway = gateway

    async def execute(self, article_headline: str, article_content: str) -> dict[str, Any]:
        """Run the analyst extraction on a single article."""
        from app.application.agents.analyst.prompt import (
            SYSTEM_PROMPT,
            validate_final_answer,
        )

        user_prompt = (
            f"Please analyze the following article and extract a Knowledge Graph and "
            f"sentiment drivers.\n\n"
            f"Headline: {article_headline!r}\n"
            f"Content: {article_content[:3000]!r}\n"
        )
        
        # We define a temporary JSON schema for the gateway's fast-path extraction
        SCHEMA = {
            "type": "object",
            "properties": {
                "type": {"const": "final_answer"},
                "knowledge_graph": {"type": "array"},
                "sentiment_drivers": {"type": "array"},
            },
            "required": ["type", "knowledge_graph", "sentiment_drivers"]
        }

        try:
            # We use complete_json directly since Analyst is a 1-step extraction
            # and doesn't currently require a multi-step tool loop.
            parsed = await self._gateway.complete_json(
                user_prompt,
                SCHEMA,
                system=SYSTEM_PROMPT,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.error("analyst_agent.failed", headline=article_headline, error=str(exc))
            return {"knowledge_graph": [], "sentiment_drivers": []}

        try:
            validate_final_answer(parsed)
        except ValueError as ve:
            logger.warning("analyst_agent.invalid_extraction", headline=article_headline, error=str(ve))
            return {"knowledge_graph": [], "sentiment_drivers": []}

        return {
            "knowledge_graph": parsed.get("knowledge_graph", []),
            "sentiment_drivers": parsed.get("sentiment_drivers", []),
        }
