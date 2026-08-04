"""Sentiment analysis orchestration use case.

Wraps the SentimentService Protocol to handle edge cases cleanly:
  - Empty content → neutral / low_confidence=True
  - Non-English content — passed through unchanged; the default model is
    multilingual so no translation step is needed at this layer.
  - Very short content (< 5 words) → result.low_confidence = True

Two-tier strategy (Phase 13 Revised):

FAST PATH  — classifier confidence ≥ LOW_CONFIDENCE_THRESHOLD AND headline/body
             agree on polarity → use the classifier result directly.

AGENTIC PATH — confidence < LOW_CONFIDENCE_THRESHOLD  OR  headline polarity
               disagrees with body polarity → AgentLoop reads article and
               reasons about sarcasm/irony/mixed framing.

FALLBACK  — AgentDidNotConvergeError → return the raw classifier label unchanged.

This module has no infrastructure imports — it depends only on
app.domain.interfaces.services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.domain.interfaces.services import SentimentResult, SentimentService

logger = structlog.get_logger(__name__)

_NEUTRAL_EMPTY = SentimentResult(label="neutral", score=0.5, low_confidence=True)

# Classifier confidence below this → route to agentic path.
LOW_CONFIDENCE_THRESHOLD: float = 0.70

ToolCallable = Callable[[dict[str, Any]], Awaitable[str]]


class AnalyzeSentiment:
    """Orchestrates per-article and batch sentiment analysis.

    Parameters
    ----------
    service:
        A SentimentService implementation (injected by the caller).
    """

    def __init__(self, service: SentimentService) -> None:
        self._service = service

    def run(self, content: str) -> SentimentResult:
        """Return a SentimentResult for *content*, never raising."""
        if not content or not content.strip():
            return _NEUTRAL_EMPTY
        try:
            return self._service.analyze(content)
        except Exception:
            return _NEUTRAL_EMPTY

    def run_batch(self, contents: list[str]) -> list[SentimentResult]:
        """Return SentimentResults for each item in *contents*, never raising."""
        if not contents:
            return []
        try:
            return self._service.analyze_batch(contents)
        except Exception:
            return [_NEUTRAL_EMPTY for _ in contents]

    async def adjudicate(
        self,
        article_id: str,
        headline_result: SentimentResult,
        body_result: SentimentResult,
        gateway: Any,
        tools: dict[str, ToolCallable],
        system_prompt: str | None = None,
    ) -> SentimentResult:
        """Run the agentic adjudication path for a low-confidence or disagreeing result.

        Parameters
        ----------
        article_id:
            DB id of the article being classified.
        headline_result:
            Classifier output for the headline text alone.
        body_result:
            Classifier output for the body text alone.
        gateway:
            LLMGateway for the agent.
        tools:
            Tool callables injected into the AgentLoop.
        system_prompt:
            Override system prompt (used in tests).

        Returns
        -------
        SentimentResult with the agent's verdict, or the *body_result* unchanged
        if the agent does not converge.
        """
        from app.application.use_cases.sentiment.prompts.agentic_sentiment import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )
        from app.application.use_cases.shared.agent_loop import (
            AgentDidNotConvergeError,
            AgentLoop,
        )

        system = system_prompt or SYSTEM_PROMPT
        loop = AgentLoop(
            gateway=gateway,
            system_prompt=system,
            tool_names=TOOL_NAMES,
            tools=tools,
            max_iterations=4,
            max_tokens_per_step=600,
            agent_name="sentiment_agent",
        )

        initial_msg = (
            f"Article ID: {article_id!r}\n"
            f"Headline classifier: label={headline_result.label!r}, "
            f"score={headline_result.score:.3f}\n"
            f"Body classifier: label={body_result.label!r}, "
            f"score={body_result.score:.3f}\n\n"
            "The classifier result is uncertain or the headline and body disagree. "
            "Read the article content carefully and produce a final_answer with the "
            "definitive sentiment_label and sentiment_score."
        )

        try:
            loop_result = await loop.run(
                initial_msg, run_id=f"sentiment:{article_id}"
            )
        except AgentDidNotConvergeError:
            logger.warning(
                "sentiment.agent_did_not_converge",
                article_id=article_id,
            )
            return body_result  # fallback: raw classifier label

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning(
                "sentiment.invalid_final_answer",
                article_id=article_id,
                error=str(ve),
            )
            return body_result  # fallback: raw classifier label

        return SentimentResult(
            label=str(final["sentiment_label"]),
            score=float(final["sentiment_score"]),
            low_confidence=False,
        )
