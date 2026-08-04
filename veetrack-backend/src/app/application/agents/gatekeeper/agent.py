"""Use case: The Gatekeeper Agent filters incoming articles based on semantic memory."""

from __future__ import annotations

from typing import Any

import structlog

from app.application.use_cases.shared.agent_loop import (
    AgentDidNotConvergeError,
    AgentLoop,
    ToolCallable,
)
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

class GatekeeperAgent:
    """Agent that filters articles by checking semantic memory (Vector DB).
    
    Parameters
    ----------
    gateway:
        LLMGateway used to run the agent.
    vector_search_tool:
        A callable that searches the Vector DB (e.g. pgvector) and returns
        JSON string representations of matching articles.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        vector_search_tool: ToolCallable,
    ) -> None:
        self._gateway = gateway
        self._tools = {
            "search_recent_memory": vector_search_tool
        }

    async def execute(self, article_headline: str, article_content: str) -> dict[str, Any]:
        """Run the gatekeeper agent for a newly scouted article."""
        from app.application.agents.gatekeeper.prompt import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )

        loop = AgentLoop(
            gateway=self._gateway,
            system_prompt=SYSTEM_PROMPT,
            tool_names=TOOL_NAMES,
            tools=self._tools,
            max_iterations=4,
            max_tokens_per_step=800,
            agent_name="gatekeeper_agent",
        )

        initial_msg = (
            f"Please evaluate this newly scouted article to see if we already know "
            f"this exact information.\n\n"
            f"Headline: {article_headline!r}\n"
            f"Content Snippet: {article_content[:1500]!r}\n\n"
            f"Use search_recent_memory to check if we have seen this before. "
            f"Return a final answer with your verdict ('accept' or 'discard')."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"gatekeeper:{article_headline[:10]}")
        except AgentDidNotConvergeError as exc:
            logger.warning("gatekeeper_agent.did_not_converge", headline=article_headline, error=str(exc))
            # On failure to converge, default to accepting it to avoid data loss
            return {"verdict": "accept", "reasoning": "Agent loop exhausted"}
        except Exception as exc:
            logger.error("gatekeeper_agent.failed", headline=article_headline, error=str(exc))
            return {"verdict": "accept", "reasoning": f"Agent error: {exc}"}

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("gatekeeper_agent.invalid_final_answer", headline=article_headline, error=str(ve))
            return {"verdict": "accept", "reasoning": "Parse error"}

        return {
            "verdict": final.get("verdict"),
            "reasoning": final.get("reasoning"),
            "matched_article_id": final.get("matched_article_id"),
        }
