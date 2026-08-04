"""Unit tests: GenerateExecutiveSummary use case."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_run_uses_fast_path_for_few_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"
    mock_gateway.complete_json = AsyncMock(
        return_value={
            "what_happened": "Apple launched a new product.",
            "why_happened": "Competition intensified in the market.",
        }
    )

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    with patch.object(use_case, "_run_agentic") as mock_agentic:
        result = await use_case.run(
            story_id="story-1",
            story_title="Apple News",
            articles=_make_articles(2),
            entity_names=["Apple"],
        )
        mock_agentic.assert_not_called()

    assert not result.skipped
    assert result.what_happened == "Apple launched a new product."
    assert result.why_happened == "Competition intensified in the market."
    assert result.model_used == "test-model"
    assert result.token_cost > 0
    assert result.reasoning_trace is None


@pytest.mark.asyncio
async def test_run_uses_agentic_path_for_many_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    with patch.object(use_case, "_run_agentic") as mock_agentic:
        # Mock what _run_agentic returns so we can assert on it
        from app.application.use_cases.insights.generate_executive_summary import (
            GenerateSummaryResult,
        )
        mock_agentic.return_value = GenerateSummaryResult(
            what_happened="Agent What",
            why_happened="Agent Why",
            model_used="agent-model",
            token_cost=100,
            reasoning_trace=[{"test": "trace"}]
        )
        
        result = await use_case.run(
            story_id="story-1",
            story_title="Apple News",
            articles=_make_articles(3),
            entity_names=["Apple"],
        )
        mock_agentic.assert_called_once()

    assert not result.skipped
    assert result.what_happened == "Agent What"
    assert result.why_happened == "Agent Why"
    assert result.reasoning_trace == [{"test": "trace"}]


@pytest.mark.asyncio
async def test_run_uses_agentic_path_for_pattern_flag() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    with patch.object(use_case, "_run_agentic") as mock_agentic:
        from app.application.use_cases.insights.generate_executive_summary import (
            GenerateSummaryResult,
        )
        mock_agentic.return_value = GenerateSummaryResult(
            what_happened="Pattern What",
            why_happened="Pattern Why",
            model_used="agent-model",
            token_cost=100,
            reasoning_trace=[{"test": "pattern_trace"}]
        )
        
        result = await use_case.run(
            story_id="story-1",
            story_title="Apple News",
            articles=_make_articles(1), # Only 1 article!
            entity_names=["Apple"],
            is_pattern=True,
        )
        mock_agentic.assert_called_once()

    assert not result.skipped
    assert result.what_happened == "Pattern What"
    assert result.reasoning_trace == [{"test": "pattern_trace"}]


@pytest.mark.asyncio
async def test_run_skips_empty_articles() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    result = await use_case.run("s", "title", [], [])

    assert result.skipped
    mock_gateway.complete_json.assert_not_called()


@pytest.mark.asyncio
async def test_run_propagates_gateway_error() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "test-model"
    mock_gateway.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    with pytest.raises(RuntimeError, match="LLM down"):
        await use_case.run("s", "t", _make_articles(2), [])


@pytest.mark.asyncio
async def test_result_includes_prompt_version() -> None:
    mock_gateway = AsyncMock()
    mock_gateway.model_name = "m"
    mock_gateway.complete_json = AsyncMock(return_value={"what_happened": "A", "why_happened": "B"})

    use_case = GenerateExecutiveSummary(gateway=mock_gateway)
    with patch.object(use_case, "_run_agentic") as mock_agentic:
        # We test the fast path to verify prompt version directly returned
        result = await use_case.run("s", "t", _make_articles(1), ["Entity1"])
    assert result.prompt_version != ""
