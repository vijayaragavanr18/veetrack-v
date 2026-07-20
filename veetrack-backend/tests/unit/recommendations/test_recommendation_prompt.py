"""Unit tests: recommendation prompt template."""

from __future__ import annotations

from app.application.use_cases.recommendations.prompts.recommendation import (
    PROMPT_VERSION,
    RESPONSE_SCHEMA,
    RecommendationPromptContext,
    build_prompt,
)


def test_build_prompt_contains_story_title() -> None:
    ctx = RecommendationPromptContext(
        title="Apple Faces Antitrust Scrutiny",
        what_happened="The FTC filed a lawsuit.",
        why_happened="Years of App Store dominance.",
        article_count=7,
        recent_headlines=["FTC sues Apple", "Apple responds"],
        entity_names=["Apple"],
    )
    _sys, user = build_prompt(ctx)
    assert "Apple Faces Antitrust Scrutiny" in user
    assert "FTC sues Apple" in user
    assert "Apple" in user


def test_build_prompt_includes_all_three_audiences_instruction() -> None:
    ctx = RecommendationPromptContext(
        title="T",
        what_happened="x",
        why_happened="y",
        article_count=5,
        recent_headlines=["h1"],
        entity_names=[],
    )
    _sys, user = build_prompt(ctx)
    assert "pr" in user.lower()
    assert "exec" in user.lower()
    assert "marketing" in user.lower()


def test_build_prompt_mentions_confidence() -> None:
    ctx = RecommendationPromptContext(
        title="T",
        what_happened="x",
        why_happened="y",
        article_count=5,
        recent_headlines=[],
        entity_names=[],
    )
    sys, _user = build_prompt(ctx)
    assert "confidence" in sys.lower()


def test_system_prompt_mentions_confidence_self_assessment() -> None:
    ctx = RecommendationPromptContext(
        title="T",
        what_happened="x",
        why_happened="y",
        article_count=3,
        recent_headlines=[],
        entity_names=[],
    )
    sys, _ = build_prompt(ctx)
    assert "self-assessment" in sys.lower() or "confidence" in sys.lower()


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION != ""


def test_response_schema_has_three_audiences() -> None:
    props = RESPONSE_SCHEMA.get("properties", {})
    assert isinstance(props, dict)
    assert "pr" in props
    assert "exec" in props
    assert "marketing" in props


def test_response_schema_requires_confidence_score() -> None:
    props = RESPONSE_SCHEMA.get("properties", {})
    assert isinstance(props, dict)
    for audience in ("pr", "exec", "marketing"):
        aud_props = props[audience].get("properties", {})  # type: ignore[union-attr]
        assert "confidence_score" in aud_props
        assert "confidence_rationale" in aud_props


def test_no_entity_names_uses_fallback() -> None:
    ctx = RecommendationPromptContext(
        title="T",
        what_happened="x",
        why_happened="y",
        article_count=3,
        recent_headlines=[],
        entity_names=[],
    )
    _, user = build_prompt(ctx)
    assert "none identified" in user


def test_headlines_capped_at_eight() -> None:
    ctx = RecommendationPromptContext(
        title="T",
        what_happened="x",
        why_happened="y",
        article_count=20,
        recent_headlines=[f"Headline {i}" for i in range(20)],
        entity_names=[],
    )
    _, user = build_prompt(ctx)
    assert "Headline 7" in user
    assert "Headline 8" not in user
