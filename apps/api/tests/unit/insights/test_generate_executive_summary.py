"""Unit tests: GenerateExecutiveSummary use case."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.insights.generate_executive_summary import (
    ArticleInput,
    GenerateExecutiveSummary,
)


def _make_articles(n: int) -> list[ArticleInput]:
    return [
        ArticleInput(
            headline=f"Headline {i}",
            published_at="2026-07-16T00:00:00+00:00",
            clean_content=f"Content {i} " * 20,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_summary_for_sufficient_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"
    mock_gateway.complete_json = AsyncMock(
        return_value={
            "what_happened": "Apple launched a new product.",
            "why_happened": "Competition intensified in the market.",
        }
    )

    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=3)
    result = await use_case.run(
        story_id="story-1",
        story_title="Apple News",
        articles=_make_articles(5),
        entity_names=["Apple"],
    )

    assert not result.skipped
    assert result.what_happened == "Apple launched a new product."
    assert result.why_happened == "Competition intensified in the market."
    assert result.model_used == "test-model"
    assert result.token_cost > 0


# ---------------------------------------------------------------------------
# Skipped — too few articles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_skips_when_too_few_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"

    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=3)
    result = await use_case.run(
        story_id="story-1",
        story_title="Short story",
        articles=_make_articles(2),
        entity_names=[],
    )

    assert result.skipped
    assert "2" in result.skip_reason
    mock_gateway.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_run_skips_empty_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"

    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=3)
    result = await use_case.run("s", "title", [], [])

    assert result.skipped
    mock_gateway.complete_json.assert_not_called()


# ---------------------------------------------------------------------------
# Gateway exception propagates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_propagates_gateway_error() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"
    mock_gateway.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=1)
    with pytest.raises(RuntimeError, match="LLM down"):
        await use_case.run("s", "t", _make_articles(3), [])


# ---------------------------------------------------------------------------
# Custom min_articles threshold respected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_min_articles_threshold_configurable() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "m"
    mock_gateway.complete_json = AsyncMock(
        return_value={"what_happened": "x", "why_happened": "y"}
    )

    # min_articles=1 — even single article should run
    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=1)
    result = await use_case.run("s", "t", _make_articles(1), [])
    assert not result.skipped


# ---------------------------------------------------------------------------
# Prompt version recorded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_includes_prompt_version() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "m"
    mock_gateway.complete_json = AsyncMock(
        return_value={"what_happened": "A", "why_happened": "B"}
    )

    use_case = GenerateExecutiveSummary(gateway=mock_gateway, min_articles=3)
    result = await use_case.run("s", "t", _make_articles(3), ["Entity1"])
    assert result.prompt_version != ""
