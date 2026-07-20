"""Use case: generate an AI executive summary (what_happened / why_happened) for a story.

Architecture notes:
  - Zero infrastructure imports — receives plain data structures as input.
  - Calls LLMGateway via the domain Protocol; does not import concrete clients.
  - Returns a GenerateSummaryResult with the parsed text + token count.
  - Caller (Celery task) is responsible for persisting to story_insights.
"""

from __future__ import annotations

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
        min_articles: int = _MIN_ARTICLES,
    ) -> None:
        self._gateway = gateway
        self._min_articles = min_articles

    async def run(
        self,
        story_id: str,
        story_title: str,
        articles: list[ArticleInput],
        entity_names: list[str],
    ) -> GenerateSummaryResult:
        if len(articles) < self._min_articles:
            logger.info(
                "generate_summary.skipped_too_few",
                story_id=story_id,
                article_count=len(articles),
                min_required=self._min_articles,
            )
            return GenerateSummaryResult(
                what_happened="",
                why_happened="",
                model_used=self._gateway.model_name,
                token_cost=0,
                skipped=True,
                skip_reason=f"only {len(articles)} articles (min {self._min_articles})",
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

        try:
            parsed = await self._gateway.complete_json(
                user_prompt,
                RESPONSE_SCHEMA,
                system=system_prompt,
                max_tokens=512,
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

        # Rough token estimate for logging when gateway doesn't report usage
        token_cost = max(1, (len(user_prompt) + len(system_prompt)) // 4)

        logger.info(
            "generate_summary.done",
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
