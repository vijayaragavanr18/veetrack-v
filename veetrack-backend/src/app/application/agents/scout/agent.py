"""Use case: The Scout Agent autonomously discovers articles via approved tools."""

from __future__ import annotations

import structlog

from app.application.use_cases.shared.agent_loop import (
    AgentDidNotConvergeError,
    AgentLoop,
    ToolCallable,
)
from app.domain.interfaces.services import LLMGateway
from app.infrastructure.mcp_client import ApiDirectMCPClient

logger = structlog.get_logger(__name__)

class ScoutAgent:
    """Agent that browses the web for a given watchlist topic.
    
    Parameters
    ----------
    gateway:
        LLMGateway used to run the agent.
    mcp_client:
        ApiDirectMCPClient used for Twitter and YouTube tool calls.
    tools:
        Standard python tools (NewsData, RSS) injected by the container.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        mcp_client: ApiDirectMCPClient,
        tools: dict[str, ToolCallable] | None = None,
    ) -> None:
        self._gateway = gateway
        self._mcp = mcp_client
        self._tools = tools or {}
        
        # Register the MCP tools dynamically
        self._tools["search_twitter_mcp"] = self._search_twitter
        self._tools["get_youtube_transcript_mcp"] = self._get_youtube

    async def _search_twitter(self, args: dict[str, Any]) -> str:
        query = args.get("query", "")
        return await self._mcp.call_tool("twitter_search", {"query": query})

    async def _get_youtube(self, args: dict[str, Any]) -> str:
        url = args.get("video_url", "")
        return await self._mcp.call_tool("youtube_transcript", {"url": url})

    async def execute(self, watchlist_topic: str) -> list[dict[str, Any]]:
        """Run the scout agent for a specific topic."""
        from app.application.agents.scout.prompt import (
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
            max_tokens_per_step=800,
            agent_name="scout_agent",
        )

        initial_msg = (
            f"Please discover recent, highly relevant information for the following "
            f"watchlist topic: {watchlist_topic!r}.\n\n"
            f"Use your tools to search NewsData, Twitter, RSS, and YouTube. "
            f"Return a final answer with the discovered items."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"scout:{watchlist_topic[:10]}")
        except AgentDidNotConvergeError as exc:
            logger.warning("scout_agent.did_not_converge", topic=watchlist_topic, error=str(exc))
            return []
        except Exception as exc:
            logger.error("scout_agent.failed", topic=watchlist_topic, error=str(exc))
            return []

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("scout_agent.invalid_final_answer", topic=watchlist_topic, error=str(ve))
            return []

        return final.get("discovered_items", [])
