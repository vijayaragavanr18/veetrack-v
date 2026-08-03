"""NLP task: near-duplicate detection for one article.

Thin Celery wrapper.  Loads the most recent N articles' MinHash signatures
from the DB, queries the LSH index, and routes to one of three paths:

  FAST PATH (duplicate)  — MinHash similarity ≥ DUPLICATE_THRESHOLD (0.75):
    Mark article as is_duplicate_of the candidate.  No LLM call.
  FAST PATH (distinct)   — MinHash similarity < DISTINCT_THRESHOLD (0.55):
    No match, article is unique.  No LLM call.
  GRAY-ZONE PATH         — similarity in [0.55, 0.75):
    Run the agentic dedup agent (ReAct loop) to decide:
    'duplicate' → mark is_duplicate_of, record dedup_verdict='duplicate'.
    'update'    → do NOT suppress; record dedup_verdict='update'.
    'distinct'  → record dedup_verdict='distinct'.
    Fallback on non-convergence → treat as the nearest threshold side
    (score ≥ midpoint → duplicate, else distinct).

Verdict and reasoning are written to dedup_verdict / dedup_reasoning /
dedup_agent_path columns added by migration 0007.

The LSH index is rebuilt in-memory per invocation (stateless workers).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from workers.celery_app import app

logger = structlog.get_logger(__name__)

_LOOKBACK_ROWS = 10_000
_GRAY_ZONE_MIDPOINT = 0.65  # fallback: score ≥ this → duplicate, else distinct


class DeduplicateSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    dedup_lookback_rows: int = _LOOKBACK_ROWS
    llm_local_endpoint: str = "http://localhost:11434/v1/chat/completions"
    llm_local_model: str = "qwen2.5:7b"


def _build_minhash(text: str) -> object:
    from datasketch import MinHash  # type: ignore[import-untyped]

    m = MinHash(num_perm=128)
    encoded = text.encode("utf-8", errors="replace")
    k = 5
    if len(encoded) < k:
        m.update(encoded)
    else:
        for i in range(len(encoded) - k + 1):
            m.update(encoded[i : i + k])
    return m


def _make_dedup_tools(session_factory: Any) -> dict[str, Any]:
    """Return the two dedup-agent tools backed by the live DB session."""

    async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        async with session_factory() as session:
            result = await session.execute(text(sql), params)
            cols = result.keys()
            return [dict(zip(cols, row, strict=True)) for row in result]

    from app.infrastructure.llm.tools.get_candidate_duplicate import (
        get_candidate_duplicate as _get_candidate,
    )
    from app.infrastructure.llm.tools.get_article_publish_gap import (
        get_article_publish_gap as _get_gap,
    )

    async def get_candidate_duplicate(args: dict[str, Any]) -> str:
        return await _get_candidate(args, _q)

    async def get_article_publish_gap(args: dict[str, Any]) -> str:
        return await _get_gap(args, _q)

    return {
        "get_candidate_duplicate": get_candidate_duplicate,
        "get_article_publish_gap": get_article_publish_gap,
    }


async def _run_agentic_dedup(
    article_id: str,
    candidate_id: str,
    jaccard_score: float,
    settings: DeduplicateSettings,
    session_factory: Any,
) -> dict[str, Any]:
    """Run the agentic dedup loop and return {'verdict', 'reasoning', 'agent_path'}."""
    from app.application.use_cases.pipeline.prompts.agentic_dedup import (
        SYSTEM_PROMPT,
        TOOL_NAMES,
        validate_final_answer,
    )
    from app.application.use_cases.shared.agent_loop import (
        AgentDidNotConvergeError,
        AgentLoop,
    )
    from app.infrastructure.llm.ollama_client import OllamaClient
    from app.infrastructure.llm.llm_gateway import RoutingLLMGateway

    local_client = OllamaClient(
        model=settings.llm_local_model,
        endpoint=settings.llm_local_endpoint,
    )
    gateway = RoutingLLMGateway(
        local_client=local_client,
        hosted_client=None,
        default_tier="local",
    )
    tools = _make_dedup_tools(session_factory)
    loop = AgentLoop(
        gateway=gateway,
        system_prompt=SYSTEM_PROMPT,
        tool_names=TOOL_NAMES,
        tools=tools,
        max_iterations=4,
        max_tokens_per_step=600,
        agent_name="dedup_agent",
    )

    initial_msg = (
        f"New article ID: {article_id!r}\n"
        f"Candidate duplicate ID: {candidate_id!r}\n"
        f"MinHash Jaccard similarity: {jaccard_score:.3f}\n\n"
        "Determine whether the new article is a duplicate, a wire-service update,"
        " or a distinct follow-up. Use the available tools to inspect content and"
        " publish gap, then produce a final_answer."
    )

    try:
        loop_result = await loop.run(
            initial_msg, run_id=f"dedup:{article_id}:{candidate_id}"
        )
    except AgentDidNotConvergeError:
        # Fallback: use score proximity
        fallback_verdict = (
            "duplicate" if jaccard_score >= _GRAY_ZONE_MIDPOINT else "distinct"
        )
        logger.warning(
            "nlp.deduplicate.agent_did_not_converge",
            article_id=article_id,
            candidate_id=candidate_id,
            jaccard_score=jaccard_score,
            fallback_verdict=fallback_verdict,
        )
        return {
            "verdict": fallback_verdict,
            "reasoning": f"Agent did not converge; fallback by score proximity ({jaccard_score:.3f})",
            "agent_path": "fallback",
        }

    final = loop_result.final_step
    try:
        validate_final_answer(final)
    except ValueError as ve:
        fallback_verdict = (
            "duplicate" if jaccard_score >= _GRAY_ZONE_MIDPOINT else "distinct"
        )
        logger.warning(
            "nlp.deduplicate.invalid_final_answer",
            article_id=article_id,
            error=str(ve),
            fallback_verdict=fallback_verdict,
        )
        return {
            "verdict": fallback_verdict,
            "reasoning": f"Invalid agent answer ({ve}); fallback by score proximity",
            "agent_path": "fallback",
        }

    return {
        "verdict": final["verdict"],
        "reasoning": final.get("reasoning", ""),
        "agent_path": "agentic",
    }


async def _run_deduplicate(
    article_id: str,
    settings: DeduplicateSettings,
) -> dict[str, Any]:
    from datasketch import MinHash, MinHashLSH  # type: ignore[import-untyped]
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.application.use_cases.pipeline.deduplicate import (
        DISTINCT_THRESHOLD,
        DUPLICATE_THRESHOLD,
        VERDICT_DISTINCT,
        VERDICT_DUPLICATE,
        VERDICT_GRAY_ZONE,
        classify_similarity,
    )

    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with factory() as session, session.begin():
            row = await session.execute(
                text("SELECT clean_content FROM articles WHERE id = :id"),
                {"id": article_id},
            )
            result = row.first()
            if result is None:
                logger.warning("nlp.deduplicate.article_not_found", article_id=article_id)
                return {"status": "not_found"}

            target_text: str = result[0] or ""
            if not target_text.strip():
                logger.info("nlp.deduplicate.skip_empty_content", article_id=article_id)
                return {"status": "skipped_empty"}

            # Build LSH index from recent non-duplicate articles
            corpus = await session.execute(
                text(
                    "SELECT id, clean_content FROM articles "
                    "WHERE id != :id AND is_duplicate_of IS NULL "
                    "AND clean_content != '' "
                    "ORDER BY ingested_at DESC "
                    "LIMIT :limit"
                ),
                {"id": article_id, "limit": settings.dedup_lookback_rows},
            )
            rows = corpus.fetchall()

            lsh: MinHashLSH = MinHashLSH(threshold=DISTINCT_THRESHOLD, num_perm=128)
            content_map: dict[str, str] = {}
            for r_id, r_text in rows:
                if not r_text:
                    continue
                m: MinHash = _build_minhash(r_text)  # type: ignore[assignment]
                import contextlib

                with contextlib.suppress(ValueError):
                    lsh.insert(r_id, m)
                content_map[r_id] = r_text

            target_minhash: MinHash = _build_minhash(target_text)  # type: ignore[assignment]
            candidates: list[str] = lsh.query(target_minhash)
            candidate_id: str | None = candidates[0] if candidates else None

            if candidate_id is None:
                # No candidate found at all → clearly distinct
                await session.execute(
                    text(
                        "UPDATE articles SET dedup_agent_path = 'fast_path', "
                        "dedup_verdict = 'distinct' WHERE id = :id"
                    ),
                    {"id": article_id},
                )
                logger.info("nlp.deduplicate.unique", article_id=article_id)
                return {
                    "status": "ok",
                    "is_duplicate": False,
                    "duplicate_of": None,
                    "verdict": VERDICT_DISTINCT,
                    "agent_path": "fast_path",
                }

            # Compute precise Jaccard score for gray-zone routing
            candidate_text = content_map.get(candidate_id, "")
            cand_hash: MinHash = _build_minhash(candidate_text)  # type: ignore[assignment]
            jaccard_score: float = float(target_minhash.jaccard(cand_hash))  # type: ignore[arg-type]
            routing = classify_similarity(jaccard_score)

            if routing == VERDICT_DUPLICATE:
                # Fast path: clearly a duplicate
                await session.execute(
                    text(
                        "UPDATE articles SET is_duplicate_of = :dup, "
                        "dedup_verdict = 'duplicate', dedup_agent_path = 'fast_path' "
                        "WHERE id = :id"
                    ),
                    {"dup": candidate_id, "id": article_id},
                )
                logger.info(
                    "nlp.deduplicate.flagged_fast",
                    article_id=article_id,
                    duplicate_of=candidate_id,
                    jaccard=jaccard_score,
                )
                return {
                    "status": "ok",
                    "is_duplicate": True,
                    "duplicate_of": candidate_id,
                    "verdict": VERDICT_DUPLICATE,
                    "agent_path": "fast_path",
                }

            if routing == VERDICT_DISTINCT:
                # Fast path: clearly distinct
                await session.execute(
                    text(
                        "UPDATE articles SET dedup_agent_path = 'fast_path', "
                        "dedup_verdict = 'distinct' WHERE id = :id"
                    ),
                    {"id": article_id},
                )
                logger.info(
                    "nlp.deduplicate.distinct_fast",
                    article_id=article_id,
                    jaccard=jaccard_score,
                )
                return {
                    "status": "ok",
                    "is_duplicate": False,
                    "duplicate_of": None,
                    "verdict": VERDICT_DISTINCT,
                    "agent_path": "fast_path",
                }

            # GRAY ZONE → agentic path (routing == VERDICT_GRAY_ZONE)
            logger.info(
                "nlp.deduplicate.gray_zone",
                article_id=article_id,
                candidate_id=candidate_id,
                jaccard=jaccard_score,
            )

        # Run agentic path outside the transaction (read-only tools)
        agentic_result = await _run_agentic_dedup(
            article_id=article_id,
            candidate_id=candidate_id,
            jaccard_score=jaccard_score,
            settings=settings,
            session_factory=factory,
        )

        verdict = agentic_result["verdict"]
        reasoning = agentic_result["reasoning"]
        agent_path = agentic_result["agent_path"]

        # Persist the verdict
        async with factory() as session, session.begin():
            if verdict == VERDICT_DUPLICATE:
                await session.execute(
                    text(
                        "UPDATE articles SET is_duplicate_of = :dup, "
                        "dedup_verdict = :v, dedup_reasoning = :r, dedup_agent_path = :ap "
                        "WHERE id = :id"
                    ),
                    {
                        "dup": candidate_id,
                        "v": verdict,
                        "r": reasoning,
                        "ap": agent_path,
                        "id": article_id,
                    },
                )
            else:
                await session.execute(
                    text(
                        "UPDATE articles SET "
                        "dedup_verdict = :v, dedup_reasoning = :r, dedup_agent_path = :ap "
                        "WHERE id = :id"
                    ),
                    {"v": verdict, "r": reasoning, "ap": agent_path, "id": article_id},
                )

        logger.info(
            "nlp.deduplicate.agentic_done",
            article_id=article_id,
            candidate_id=candidate_id,
            verdict=verdict,
            agent_path=agent_path,
            jaccard=jaccard_score,
        )
        return {
            "status": "ok",
            "is_duplicate": verdict == VERDICT_DUPLICATE,
            "duplicate_of": candidate_id if verdict == VERDICT_DUPLICATE else None,
            "verdict": verdict,
            "agent_path": agent_path,
        }

    finally:
        await engine.dispose()


@app.task(
    name="tasks.nlp.deduplicate.run",
    queue="nlp",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run(self: object, *, article_id: str) -> dict[str, Any]:  # type: ignore[misc]
    """Flag article *article_id* as duplicate/update/distinct via two-tier dedup."""
    settings = DeduplicateSettings()
    if not settings.database_url:
        logger.warning("nlp.deduplicate.no_database_url", article_id=article_id)
        return {"status": "no_database_url"}

    try:
        return asyncio.run(_run_deduplicate(article_id, settings))
    except Exception as exc:
        logger.error("nlp.deduplicate.failed", article_id=article_id, error=str(exc))
        raise
