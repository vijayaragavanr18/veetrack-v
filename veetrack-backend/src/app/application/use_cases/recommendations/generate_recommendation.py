"""Use case: generate audience-specific recommendations for a story.

Zero infrastructure imports — receives plain data and calls LLMGateway via Protocol.

Two execution paths:

  AGENTIC PATH  — runs the ReAct loop (RecommendationAgent) for stories that cross a
  deliberation threshold: any high/critical risk story, or an entity's first significant
  event in 30 days.  The agent may call up to 4 contextual tools before committing to a
  recommendation and logs a full reasoning_trace per the architecture addendum.

  SINGLE-SHOT PATH  — the original one-call approach for routine low/medium-risk stories.
  Also used as the automatic fallback if the agent loop raises AgentLoopError.

Hybrid trigger rationale: most stories don't need multi-step reasoning.  Running the
expensive agentic path on everything would slow the pipeline for no quality gain on
easy cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from app.application.use_cases.recommendations.prompts.recommendation import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    RecommendationPromptContext,
    build_prompt,
)
from app.application.use_cases.recommendations.recommendation_agent import (
    AgentLoopError,
    RecommendationAgent,
    ToolCallable,
)
from app.domain.entities import RecommendationAudience, RiskLevel
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.65
_VALID_AUDIENCES: list[RecommendationAudience] = ["pr", "exec", "marketing"]
_VALID_RISK_LEVELS: list[RiskLevel] = ["low", "medium", "high", "critical"]
_AGENTIC_RISK_LEVELS: set[str] = {"high", "critical"}


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
    agent_mode: str  # "agentic" | "single_shot"
    reasoning_trace: list[dict[str, Any]] = field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class GenerateRecommendationsOutput:
    results: list[RecommendationResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


def _should_run_agentic(risk_level: str, days_since_last_event: int | None) -> bool:
    """Return True when the story warrants the full ReAct loop.

    Agentic path triggers on:
    - High or critical risk level (genuine deliberation needed).
    - Entity has no similar event in the past 30 days (first major event — context
      gathering avoids cold-start recommendation errors).
    """
    if risk_level in _AGENTIC_RISK_LEVELS:
        return True
    if days_since_last_event is None or days_since_last_event > 30:
        return True
    return False


def _coerce_risk(raw: str) -> RiskLevel:
    low = raw.lower()
    return low if low in _VALID_RISK_LEVELS else "low"  # type: ignore[return-value]


def _coerce_score(raw: Any) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


class GenerateRecommendation:
    """Generate PR/exec/marketing recommendations for a story cluster.

    Parameters
    ----------
    gateway:
        LLMGateway implementation.
    confidence_threshold:
        Recommendations with confidence_score < threshold get needs_human_review=True.
    min_articles:
        Minimum articles before attempting generation.
    tools:
        Optional dict of tool_name → async callable for the agentic path.
        If omitted, all tool calls will return "unavailable" gracefully.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        min_articles: int = 3,
        tools: dict[str, ToolCallable] | None = None,
    ) -> None:
        self._gateway = gateway
        self._confidence_threshold = confidence_threshold
        self._min_articles = min_articles
        self._tools: dict[str, ToolCallable] = tools or {}

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
        # Optional fields for the hybrid trigger decision
        entity_id: str = "",
        risk_level: str = "low",
        days_since_last_event: int | None = None,
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

        use_agentic = _should_run_agentic(risk_level, days_since_last_event)

        if use_agentic:
            result = await self._run_agentic(
                story_id=story_id,
                entity_id=entity_id,
                story_title=story_title,
                what_happened=what_happened,
                why_happened=why_happened,
                article_count=article_count,
                recent_headlines=recent_headlines,
                entity_names=entity_names,
                risk_level=risk_level,
            )
            if result is not None:
                return result
            # AgentLoopError was caught — fall through to single-shot

        return await self._run_single_shot(
            story_id=story_id,
            story_title=story_title,
            what_happened=what_happened,
            why_happened=why_happened,
            article_count=article_count,
            recent_headlines=recent_headlines,
            entity_names=entity_names,
        )

    # ── Agentic path ──────────────────────────────────────────────────────────

    async def _run_agentic(
        self,
        story_id: str,
        entity_id: str,
        story_title: str,
        what_happened: str,
        why_happened: str,
        article_count: int,
        recent_headlines: list[str],
        entity_names: list[str],
        risk_level: str,
    ) -> GenerateRecommendationsOutput | None:
        """Run the ReAct loop.  Returns None on AgentLoopError (triggers fallback)."""
        agent = RecommendationAgent(
            gateway=self._gateway,
            tools=self._tools,
            max_tokens_per_step=600,
        )
        try:
            agent_result = await agent.run(
                story_id=story_id,
                entity_id=entity_id,
                story_title=story_title,
                what_happened=what_happened,
                why_happened=why_happened,
                article_count=article_count,
                recent_headlines=recent_headlines,
                entity_names=entity_names,
                risk_level=risk_level,
            )
        except AgentLoopError as exc:
            logger.warning(
                "generate_recommendation.agent_loop_exhausted",
                story_id=story_id,
                error=str(exc),
            )
            return None
        except Exception as exc:
            logger.error(
                "generate_recommendation.agent_failed",
                story_id=story_id,
                error=str(exc),
            )
            return None

        results: list[RecommendationResult] = []
        for audience, raw_rec in [("pr", agent_result.pr), ("exec", agent_result.exec_), ("marketing", agent_result.marketing)]:
            rec_text = str(raw_rec.get("recommendation_text", "")).strip()
            risk: RiskLevel = _coerce_risk(str(raw_rec.get("risk_level", "low")))
            confidence = _coerce_score(raw_rec.get("confidence_score", 0.0))
            rationale = str(raw_rec.get("confidence_rationale", "")).strip()
            needs_review = confidence < self._confidence_threshold

            results.append(
                RecommendationResult(
                    audience=audience,  # type: ignore[arg-type]
                    recommendation_text=rec_text,
                    risk_level=risk,
                    confidence_score=confidence,
                    confidence_rationale=rationale,
                    needs_human_review=needs_review,
                    model_used=self._gateway.model_name,
                    agent_mode="agentic",
                    reasoning_trace=agent_result.trace,
                )
            )

        logger.info(
            "generate_recommendation.agentic_done",
            story_id=story_id,
            iterations=agent_result.iterations_used,
            audiences=len(results),
            pending_review=sum(1 for r in results if r.needs_human_review),
            model=self._gateway.model_name,
        )
        return GenerateRecommendationsOutput(results=results)

    # ── Single-shot path ──────────────────────────────────────────────────────

    async def _run_single_shot(
        self,
        story_id: str,
        story_title: str,
        what_happened: str,
        why_happened: str,
        article_count: int,
        recent_headlines: list[str],
        entity_names: list[str],
    ) -> GenerateRecommendationsOutput:
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
                "generate_recommendation.single_shot_failed",
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
            risk: RiskLevel = _coerce_risk(str(raw.get("risk_level", "low")))
            confidence = _coerce_score(raw.get("confidence_score", 0.0))
            rationale = str(raw.get("confidence_rationale", "")).strip()
            needs_review = confidence < self._confidence_threshold

            results.append(
                RecommendationResult(
                    audience=audience,
                    recommendation_text=rec_text,
                    risk_level=risk,
                    confidence_score=confidence,
                    confidence_rationale=rationale,
                    needs_human_review=needs_review,
                    model_used=self._gateway.model_name,
                    agent_mode="single_shot",
                    reasoning_trace=[],
                )
            )

        logger.info(
            "generate_recommendation.single_shot_done",
            story_id=story_id,
            audiences=len(results),
            pending_review=sum(1 for r in results if r.needs_human_review),
            model=self._gateway.model_name,
        )
        return GenerateRecommendationsOutput(results=results)
