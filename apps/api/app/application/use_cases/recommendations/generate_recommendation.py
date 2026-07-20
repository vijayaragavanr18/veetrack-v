"""Use case: generate audience-specific recommendations for a story.

Zero infrastructure imports — receives plain data and calls LLMGateway via Protocol.
Returns a list of RecommendationResult (one per audience), with needs_human_review set
by the caller-configurable confidence threshold.

The confidence threshold defaults to 0.65; configure via RECOMMENDATION_CONFIDENCE_THRESHOLD env var.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.application.use_cases.recommendations.prompts.recommendation import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    RecommendationPromptContext,
    build_prompt,
)
from app.domain.entities import RecommendationAudience, RiskLevel
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.65
_VALID_AUDIENCES: list[RecommendationAudience] = ["pr", "exec", "marketing"]
_VALID_RISK_LEVELS: list[RiskLevel] = ["low", "medium", "high", "critical"]


@dataclass
class ArticleHeadline:
    headline: str


@dataclass
class RecommendationResult:
    audience: RecommendationAudience
    recommendation_text: str
    risk_level: RiskLevel
    confidence_score: float
    confidence_rationale: str
    needs_human_review: bool
    model_used: str
    prompt_version: str = PROMPT_VERSION
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class GenerateRecommendationsOutput:
    results: list[RecommendationResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class GenerateRecommendation:
    """Generate PR/exec/marketing recommendations for a story cluster.

    Parameters
    ----------
    gateway:
        LLMGateway implementation. Hosted tier used by default (better quality).
    confidence_threshold:
        Recommendations with confidence_score < threshold get needs_human_review=True.
    min_articles:
        Minimum articles before attempting generation.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        min_articles: int = 3,
    ) -> None:
        self._gateway = gateway
        self._confidence_threshold = confidence_threshold
        self._min_articles = min_articles

    @property
    def confidence_threshold(self) -> float:
        return self._confidence_threshold

    async def run(
        self,
        story_id: str,
        story_title: str,
        what_happened: str,
        why_happened: str,
        article_count: int,
        recent_headlines: list[str],
        entity_names: list[str],
    ) -> GenerateRecommendationsOutput:
        if article_count < self._min_articles:
            logger.info(
                "generate_recommendation.skipped_too_few",
                story_id=story_id,
                count=article_count,
            )
            return GenerateRecommendationsOutput(
                skipped=True,
                skip_reason=f"only {article_count} articles (min {self._min_articles})",
            )

        ctx = RecommendationPromptContext(
            title=story_title,
            what_happened=what_happened,
            why_happened=why_happened,
            article_count=article_count,
            recent_headlines=recent_headlines,
            entity_names=entity_names,
        )
        system_prompt, user_prompt = build_prompt(ctx)

        try:
            parsed = await self._gateway.complete_json(
                user_prompt,
                RESPONSE_SCHEMA,
                system=system_prompt,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.error(
                "generate_recommendation.llm_failed",
                story_id=story_id,
                error=str(exc),
            )
            raise

        results: list[RecommendationResult] = []
        for audience in _VALID_AUDIENCES:
            raw = parsed.get(audience, {})
            if not isinstance(raw, dict):
                continue

            rec_text = str(raw.get("recommendation_text", "")).strip()
            risk_raw = str(raw.get("risk_level", "low")).lower()
            risk_level: RiskLevel = risk_raw if risk_raw in _VALID_RISK_LEVELS else "low"  # type: ignore[assignment]
            confidence = float(raw.get("confidence_score", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            rationale = str(raw.get("confidence_rationale", "")).strip()
            needs_review = confidence < self._confidence_threshold

            results.append(
                RecommendationResult(
                    audience=audience,
                    recommendation_text=rec_text,
                    risk_level=risk_level,
                    confidence_score=confidence,
                    confidence_rationale=rationale,
                    needs_human_review=needs_review,
                    model_used=self._gateway.model_name,
                )
            )

        logger.info(
            "generate_recommendation.done",
            story_id=story_id,
            audiences=len(results),
            pending_review=sum(1 for r in results if r.needs_human_review),
            model=self._gateway.model_name,
        )
        return GenerateRecommendationsOutput(results=results)
