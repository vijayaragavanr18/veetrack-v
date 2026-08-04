"""Use case: The Synthesizer Agent organizes articles into storylines."""

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

class SynthesizerAgent:
    """Agent that acts as a News Editor, grouping articles into evolving Storylines.
    
    Parameters
    ----------
    gateway:
        LLMGateway used to run the agent.
    get_storylines_tool:
        A callable that fetches current active storylines for an entity.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        get_storylines_tool: ToolCallable,
    ) -> None:
        self._gateway = gateway
        self._tools = {
            "get_active_storylines": get_storylines_tool
        }

    async def execute(self, entity_id: str, article_headline: str, analyst_kg: list[dict[str, Any]]) -> dict[str, Any]:
        """Run the synthesizer agent to place the new article."""
        from app.application.agents.synthesizer.prompt import (
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
            agent_name="synthesizer_agent",
        )

        initial_msg = (
            f"A new article has been analyzed for entity {entity_id!r}.\n\n"
            f"Headline: {article_headline!r}\n"
            f"Extracted Knowledge Graph: {analyst_kg!r}\n\n"
            f"Use get_active_storylines to see if this fits an existing narrative. "
            f"Return a final answer with your synthesis decision."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"synth:{entity_id[:8]}")
        except AgentDidNotConvergeError as exc:
            logger.warning("synthesizer_agent.did_not_converge", entity=entity_id, error=str(exc))
            # Fallback: create a new storyline if confused
            return {"action": "create", "new_storyline_title": article_headline, "reasoning": "Fallback due to agent timeout."}
        except Exception as exc:
            logger.error("synthesizer_agent.failed", entity=entity_id, error=str(exc))
            return {"action": "create", "new_storyline_title": article_headline, "reasoning": f"Agent error: {exc}"}

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("synthesizer_agent.invalid_final_answer", entity=entity_id, error=str(ve))
            return {"action": "create", "new_storyline_title": article_headline, "reasoning": "Parse error."}

        return {
            "action": final.get("action"),
            "storyline_id": final.get("storyline_id"),
            "new_storyline_title": final.get("new_storyline_title"),
            "reasoning": final.get("reasoning"),
        }
