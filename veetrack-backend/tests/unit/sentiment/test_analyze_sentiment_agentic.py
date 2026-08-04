"""Unit tests for the agentic adjudication path in AnalyzeSentiment."""

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.sentiment.analyze_sentiment import AnalyzeSentiment
from app.domain.interfaces.services import SentimentResult
from app.infrastructure.llm.tools.get_classifier_breakdown import get_classifier_breakdown
from app.infrastructure.llm.tools.get_entity_sentiment_baseline import get_entity_sentiment_baseline


@pytest.mark.asyncio
async def test_adjudicate_successful_convergence():
    uc = AnalyzeSentiment(AsyncMock())
    
    headline_res = SentimentResult(label="positive", score=0.6)
    body_res = SentimentResult(label="negative", score=0.9)
    
    gateway = AsyncMock()
    # Return a final answer immediately
    gateway.complete.return_value = '''
    {
      "type": "final_answer",
      "sentiment_label": "negative",
      "sentiment_score": 0.85,
      "reasoning": "The headline is clickbait, but the body clearly outlines a terrible earnings report."
    }
    '''
    
    result = await uc.adjudicate(
        article_id="art-123",
        headline_result=headline_res,
        body_result=body_res,
        gateway=gateway,
        tools={},
    )
    
    assert result.label == "negative"
    assert result.score == 0.85
    assert result.low_confidence is False


@pytest.mark.asyncio
async def test_adjudicate_fallback_on_invalid_json():
    uc = AnalyzeSentiment(AsyncMock())
    
    headline_res = SentimentResult(label="positive", score=0.6)
    body_res = SentimentResult(label="neutral", score=0.8)
    
    gateway = AsyncMock()
    # Return garbage that causes parse error and eventually fails to converge
    gateway.complete.return_value = "I am an AI, I think it is positive."
    
    result = await uc.adjudicate(
        article_id="art-123",
        headline_result=headline_res,
        body_result=body_res,
        gateway=gateway,
        tools={},
    )
    
    # Fallback to body_result
    assert result.label == "neutral"
    assert result.score == 0.8
    assert result.low_confidence is False


@pytest.mark.asyncio
async def test_get_classifier_breakdown_tool():
    db_query = AsyncMock()
    db_query.return_value = [
        {
            "id": "art-123",
            "headline": "Company XYZ soars",
            "clean_content": "XYZ stock is up 100%.",
            "sentiment_label": "positive",
            "sentiment_score": 0.95
        }
    ]
    
    args = {"article_id": "art-123"}
    res = await get_classifier_breakdown(args, db_query)
    assert "Company XYZ soars" in res
    assert "0.950" in res


@pytest.mark.asyncio
async def test_get_entity_sentiment_baseline_tool():
    db_query = AsyncMock()
    # First call is entity, second call is sentiment rows
    db_query.side_effect = [
        [{"canonical_name": "Company XYZ", "type": "company"}],
        [
            {"sentiment_label": "positive"},
            {"sentiment_label": "positive"},
            {"sentiment_label": "negative"}
        ]
    ]
    
    args = {"entity_id": "ent-123"}
    res = await get_entity_sentiment_baseline(args, db_query)
    assert "Company XYZ" in res
    assert "positive: 2" in res
    assert "negative: 1" in res
    assert "dominant_label: 'positive'" in res

