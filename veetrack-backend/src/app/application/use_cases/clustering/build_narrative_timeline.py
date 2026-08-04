"""Use case: Build Narrative Timeline.

Given a list of articles in a story, this use case builds a narrative timeline
identifying key turning points.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ToolCallable = Callable[[dict[str, Any]], Awaitable[str]]

class BuildNarrativeTimeline:
    """Builds a narrative timeline for a story using the AgentLoop."""
    
    def __init__(
        self,
        gateway: Any,
        tools: dict[str, ToolCallable],
    ) -> None:
        self._gateway = gateway
        self._tools = tools

    async def run(
        self,
        story_id: str,
    ) -> dict[str, Any]:
        """Run the agentic path to build a narrative timeline."""
        from app.application.use_cases.shared.agent_loop import (
            AgentDidNotConvergeError,
            AgentLoop,
        )
        from app.application.use_cases.shared.prompts.agentic_clustering import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )

        loop = AgentLoop(
            gateway=self._gateway,
            system_prompt=SYSTEM_PROMPT,
            tool_names=TOOL_NAMES,
            tools=self._tools,
            max_iterations=6,
            max_tokens_per_step=600,
            agent_name="clustering_agent",
        )

        initial_msg = (
            f"Story ID: {story_id!r}\n\n"
            "Analyze the timeline of this story and produce a final_answer "
            "identifying the timeline highlights (key turning points)."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"timeline:{story_id}")
        except AgentDidNotConvergeError:
            logger.warning("timeline.agent_did_not_converge", story_id=story_id)
            return {"timeline_highlights": []}

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("timeline.invalid_final_answer", story_id=story_id, error=str(ve))
            return {"timeline_highlights": []}

        return {"timeline_highlights": final.get("timeline_highlights", [])}
