"""Use case: generate an AI executive summary (what_happened / why_happened) for a story.

Architecture notes:
  - Zero infrastructure imports — receives plain data structures as input.
  - Calls LLMGateway via the domain Protocol; does not import concrete clients.
  - Returns a GenerateSummaryResult with the parsed text + token count.
  - Caller (Celery task) is responsible for persisting to story_insights.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass

import structlog

from app.application.use_cases.insights.prompts.executive_summary import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    ArticleSummary,
    build_prompt,
)
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

_MIN_ARTICLES = 3  # don't generate a summary unless the story has meaningful depth


@dataclass
class ArticleInput:
    headline: str
    published_at: str
    clean_content: str


@dataclass
class GenerateSummaryResult:
    what_happened: str
    why_happened: str
    model_used: str
    token_cost: int
    skipped: bool = False
    skip_reason: str = ""
    prompt_version: str = PROMPT_VERSION
    reasoning_trace: list[dict[str, Any]] | None = None


class GenerateExecutiveSummary:
    """Generate and return an executive summary for a story cluster.

    Parameters
    ----------
    gateway:
        LLMGateway implementation (routing gateway or a stub for tests).
    min_articles:
        Minimum number of articles required before generating a summary.
        Stories with fewer articles return a skipped result.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        tools: dict[str, Any] | None = None,
    ) -> None:
        self._gateway = gateway
        self.tools = tools or {}

    async def run(
        self,
        story_id: str,
        story_title: str,
        articles: list[ArticleInput],
        entity_names: list[str],
        primary_entity_id: str = "",
        is_pattern: bool = False,
    ) -> GenerateSummaryResult:
        if not articles:
            return GenerateSummaryResult(
                what_happened="",
                why_happened="",
                model_used=self._gateway.model_name,
                token_cost=0,
                skipped=True,
                skip_reason="no articles",
            )

        article_summaries = [
            ArticleSummary(
                headline=a.headline,
                published_at=a.published_at,
                content_snippet=a.clean_content[:300],
            )
            for a in articles
        ]

        system_prompt, user_prompt = build_prompt(
            title=story_title,
            articles=article_summaries,
            entity_names=entity_names,
        )

        # Always use the fast path with the local Qwen2.5 7B model for speed
        return await self._run_fast_path(
            story_id=story_id,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    async def _run_fast_path(self, story_id: str, system_prompt: str, user_prompt: str) -> GenerateSummaryResult:
        try:
            parsed = await self._gateway.complete_json(
                user_prompt,
                RESPONSE_SCHEMA,
                system=system_prompt,
                max_tokens=512,
                model_tier="local",
            )
        except Exception as exc:
            logger.error(
                "generate_summary.llm_failed",
                story_id=story_id,
                error=str(exc),
            )
            raise

        what_happened = str(parsed.get("what_happened", "")).strip()
        why_happened = str(parsed.get("why_happened", "")).strip()
        token_cost = max(1, (len(user_prompt) + len(system_prompt)) // 4)

        logger.info(
            "generate_summary.fast_path.done",
            story_id=story_id,
            model=self._gateway.model_name,
            token_cost=token_cost,
        )

        return GenerateSummaryResult(
            what_happened=what_happened,
            why_happened=why_happened,
            model_used=self._gateway.model_name,
            token_cost=token_cost,
        )

    async def _run_agentic(
        self,
        story_id: str,
        primary_entity_id: str,
        system_prompt: str,
        user_prompt: str,
    ) -> GenerateSummaryResult:
        from app.application.use_cases.shared.agent_loop import (
            AgentDidNotConvergeError,
            AgentLoop,
        )
        from app.application.use_cases.shared.prompts.agentic_executive_brief import (
            SYSTEM_PROMPT as AGENT_SYSTEM_PROMPT,
        )
        from app.application.use_cases.shared.prompts.agentic_executive_brief import (
            TOOL_NAMES,
            validate_final_answer,
        )

        loop = AgentLoop(
            gateway=self._gateway,
            system_prompt=AGENT_SYSTEM_PROMPT,
            tool_names=TOOL_NAMES,
            tools=self.tools,
            max_iterations=5,
            max_tokens_per_step=800,
            agent_name="executive_brief_agent",
        )

        initial_msg = (
            f"Please generate an executive brief for this story.\n"
            f"The primary entity ID is: {primary_entity_id!r}.\n"
            f"Here is the context provided so far:\n\n"
            f"{system_prompt}\n\n{user_prompt}\n"
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"brief:{story_id}")
        except AgentDidNotConvergeError:
            logger.warning("generate_summary.agent_did_not_converge", story_id=story_id)
            return await self._run_fast_path(story_id, system_prompt, user_prompt)

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("generate_summary.invalid_final_answer", story_id=story_id, error=str(ve))
            return await self._run_fast_path(story_id, system_prompt, user_prompt)

        what_happened = str(final.get("what_happened", "")).strip()
        why_happened = str(final.get("why_happened", "")).strip()

        token_cost = max(1, (len(user_prompt) + len(system_prompt)) // 4) * loop_result.iterations_used

        logger.info(
            "generate_summary.agentic.done",
            story_id=story_id,
            model=self._gateway.model_name,
            token_cost=token_cost,
            iterations=loop_result.iterations_used,
        )

        return GenerateSummaryResult(
            what_happened=what_happened,
            why_happened=why_happened,
            model_used=self._gateway.model_name,
            token_cost=token_cost,
            reasoning_trace=loop_result.trace,
        )
