"""Unit tests for the agentic dedup agent (Phase 11 revised).

Tests cover:
  - Gray-zone band boundaries: correct fast-path vs agentic routing.
  - compute_jaccard_similarity helper.
  - classify_similarity at boundaries and interior.
  - Tool functions (get_candidate_duplicate, get_article_publish_gap) against fakes.
  - validate_final_answer: valid and invalid shapes.
  - Architecture: prompt file and use case have no infra imports.

No infrastructure imports. All I/O via fakes.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

import pytest

from app.application.use_cases.pipeline.deduplicate import (
    DISTINCT_THRESHOLD,
    DUPLICATE_THRESHOLD,
    VERDICT_DISTINCT,
    VERDICT_DUPLICATE,
    VERDICT_GRAY_ZONE,
    classify_similarity,
    compute_jaccard_similarity,
)
from app.application.use_cases.pipeline.prompts.agentic_dedup import validate_final_answer

# ── classify_similarity ───────────────────────────────────────────────────────


class TestClassifySimilarity:
    def test_above_duplicate_threshold_is_duplicate(self) -> None:
        assert classify_similarity(DUPLICATE_THRESHOLD) == VERDICT_DUPLICATE
        assert classify_similarity(1.0) == VERDICT_DUPLICATE
        assert classify_similarity(0.9) == VERDICT_DUPLICATE

    def test_below_distinct_threshold_is_distinct(self) -> None:
        assert classify_similarity(0.0) == VERDICT_DISTINCT
        assert classify_similarity(DISTINCT_THRESHOLD - 0.01) == VERDICT_DISTINCT

    def test_in_gray_zone(self) -> None:
        mid = (DISTINCT_THRESHOLD + DUPLICATE_THRESHOLD) / 2
        assert classify_similarity(mid) == VERDICT_GRAY_ZONE

    def test_at_distinct_threshold_is_gray_zone(self) -> None:
        # DISTINCT_THRESHOLD itself is inside the gray zone (score >= DISTINCT_THRESHOLD)
        assert classify_similarity(DISTINCT_THRESHOLD) == VERDICT_GRAY_ZONE

    def test_just_below_duplicate_threshold_is_gray_zone(self) -> None:
        assert classify_similarity(DUPLICATE_THRESHOLD - 0.01) == VERDICT_GRAY_ZONE

    def test_boundary_values_are_deterministic(self) -> None:
        # Ensure thresholds are fixed at expected values
        assert pytest.approx(0.55) == DISTINCT_THRESHOLD
        assert pytest.approx(0.75) == DUPLICATE_THRESHOLD


# ── compute_jaccard_similarity ────────────────────────────────────────────────


class TestComputeJaccardSimilarity:
    def test_identical_texts_high_similarity(self) -> None:
        text = "Apple reports record quarterly revenue driven by iPhone sales."
        score = compute_jaccard_similarity(text, text)
        assert score == pytest.approx(1.0)

    def test_unrelated_texts_low_similarity(self) -> None:
        a = "Tesla unveils new Cybertruck with extended-range battery option."
        b = "European Central Bank holds rates steady amid inflation uncertainty."
        score = compute_jaccard_similarity(a, b)
        assert score < DISTINCT_THRESHOLD

    def test_near_identical_long_texts_above_distinct_threshold(self) -> None:
        base = (
            "Microsoft Azure cloud revenue grew thirty percent year over year in the most recent "
            "quarter, beating Wall Street expectations by a significant margin. The company's "
            "chief financial officer credited enterprise AI workload adoption and expanding data "
            "centre capacity across Europe and Asia Pacific regions."
        )
        variant = base + " Analysts noted strong momentum heading into the holiday quarter."
        score = compute_jaccard_similarity(base, variant)
        assert score > DISTINCT_THRESHOLD

    def test_returns_float_in_zero_one(self) -> None:
        score = compute_jaccard_similarity("hello", "world")
        assert 0.0 <= score <= 1.0


# ── validate_final_answer ─────────────────────────────────────────────────────


class TestValidateFinalAnswer:
    def test_valid_duplicate(self) -> None:
        validate_final_answer({
            "type": "final_answer",
            "verdict": "duplicate",
            "reasoning": "Same content, same-hour publish gap.",
        })

    def test_valid_update(self) -> None:
        validate_final_answer({
            "type": "final_answer",
            "verdict": "update",
            "reasoning": "New earnings figure added to existing story.",
        })

    def test_valid_distinct(self) -> None:
        validate_final_answer({
            "type": "final_answer",
            "verdict": "distinct",
            "reasoning": "Multi-day gap, different angle on same company.",
        })

    def test_wrong_type(self) -> None:
        with pytest.raises(ValueError, match='Expected type="final_answer"'):
            validate_final_answer({"type": "tool_call", "verdict": "duplicate", "reasoning": "x"})

    def test_invalid_verdict(self) -> None:
        with pytest.raises(ValueError, match="Invalid verdict"):
            validate_final_answer({
                "type": "final_answer",
                "verdict": "merge",
                "reasoning": "not a valid verdict",
            })

    def test_missing_reasoning(self) -> None:
        with pytest.raises(ValueError, match='"reasoning"'):
            validate_final_answer({"type": "final_answer", "verdict": "duplicate", "reasoning": ""})

    def test_missing_verdict(self) -> None:
        with pytest.raises(ValueError, match="Invalid verdict"):
            validate_final_answer({
                "type": "final_answer",
                "verdict": None,
                "reasoning": "some reasoning",
            })


# ── Tool: get_candidate_duplicate ────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetCandidateDuplicate:
    async def test_not_found(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_duplicate import get_candidate_duplicate

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_candidate_duplicate({"article_id": "missing"}, _q)
        assert "no article" in result.lower() or "missing" in result

    async def test_returns_headline_and_preview(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_duplicate import get_candidate_duplicate

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{
                "id": "art-1",
                "headline": "Apple reports Q4 results",
                "publisher": "Reuters",
                "published_at": "2026-07-21 10:00:00",
                "clean_content": "Apple reported strong earnings for Q4.",
                "is_duplicate_of": None,
            }]

        result = await get_candidate_duplicate({"article_id": "art-1"}, _q)
        assert "Apple reports Q4 results" in result
        assert "Reuters" in result
        assert "Apple reported strong earnings" in result

    async def test_long_content_is_truncated(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_duplicate import (
            _CONTENT_PREVIEW_CHARS,
            get_candidate_duplicate,
        )

        long_content = "x" * (_CONTENT_PREVIEW_CHARS + 100)

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{
                "id": "art-1",
                "headline": "Test",
                "publisher": "Test",
                "published_at": "2026-07-21",
                "clean_content": long_content,
                "is_duplicate_of": None,
            }]

        result = await get_candidate_duplicate({"article_id": "art-1"}, _q)
        assert "truncated" in result.lower() or "…" in result


# ── Tool: get_article_publish_gap ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetArticlePublishGap:
    async def test_missing_articles(self) -> None:
        from app.infrastructure.llm.tools.get_article_publish_gap import get_article_publish_gap

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"id": "art-1", "published_at": "2026-07-21 10:00:00"}]

        result = await get_article_publish_gap(
            {"article_id_a": "art-1", "article_id_b": "art-missing"}, _q
        )
        assert "missing" in result.lower() or "could not" in result.lower()

    async def test_both_missing(self) -> None:
        from app.infrastructure.llm.tools.get_article_publish_gap import get_article_publish_gap

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_article_publish_gap(
            {"article_id_a": "a", "article_id_b": "b"}, _q
        )
        assert "missing" in result.lower() or "could not" in result.lower()

    async def test_datetime_objects_compute_gap(self) -> None:
        from datetime import datetime

        from app.infrastructure.llm.tools.get_article_publish_gap import get_article_publish_gap

        t1 = datetime(2026, 7, 21, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 7, 21, 10, 30, 0, tzinfo=UTC)

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {"id": "art-1", "published_at": t1},
                {"id": "art-2", "published_at": t2},
            ]

        result = await get_article_publish_gap(
            {"article_id_a": "art-1", "article_id_b": "art-2"}, _q
        )
        # 30-minute gap → same-hour → "wire retransmission" hint
        assert "30m" in result or "wire" in result.lower() or "same-hour" in result.lower()

    async def test_multiday_gap_signals_distinct(self) -> None:
        from datetime import datetime

        from app.infrastructure.llm.tools.get_article_publish_gap import get_article_publish_gap

        t1 = datetime(2026, 7, 18, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 7, 21, 10, 0, 0, tzinfo=UTC)  # 3 days later

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {"id": "art-1", "published_at": t1},
                {"id": "art-2", "published_at": t2},
            ]

        result = await get_article_publish_gap(
            {"article_id_a": "art-1", "article_id_b": "art-2"}, _q
        )
        assert "3d" in result or "distinct" in result.lower() or "multi-day" in result.lower()


# ── Architecture checks ───────────────────────────────────────────────────────


class TestArchitecture:
    def test_agentic_dedup_prompt_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/pipeline/prompts/agentic_dedup.py"
        )
        tree = ast.parse(src.read_text())
        bad_prefixes = ("app.infrastructure", "sqlalchemy", "fastapi", "redis")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    for bad in bad_prefixes:
                        assert not (name or "").startswith(bad), (
                            f"agentic_dedup prompt imports {name!r} (infra violation)"
                        )

    def test_deduplicate_use_case_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/pipeline/deduplicate.py"
        )
        tree = ast.parse(src.read_text())
        bad_prefixes = ("app.infrastructure", "sqlalchemy", "fastapi", "redis")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module or ""] if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                for name in names:
                    for bad in bad_prefixes:
                        assert not (name or "").startswith(bad), (
                            f"deduplicate use case imports {name!r} (infra violation)"
                        )
