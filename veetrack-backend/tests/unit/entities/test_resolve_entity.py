"""Unit tests: ResolveEntity use case — pure logic, no real DB."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.entities.resolve_entity import (
    ResolveEntity,
    label_to_entity_type,
    trigram_similarity,
)
from app.domain.entities import Entity
from app.domain.interfaces.services import EntityMention

# ---------------------------------------------------------------------------
# trigram_similarity helpers
# ---------------------------------------------------------------------------


def test_trigram_similarity_identical() -> None:
    assert trigram_similarity("Tesla", "Tesla") == pytest.approx(1.0)


def test_trigram_similarity_different() -> None:
    assert trigram_similarity("Tesla", "Apple") < 0.3


def test_trigram_similarity_case_insensitive() -> None:
    assert trigram_similarity("TSLA", "tsla") == pytest.approx(1.0)


def test_trigram_similarity_near_match() -> None:
    score = trigram_similarity("Tesla Inc.", "Tesla Inc")
    assert score > 0.7


def test_trigram_similarity_short_text() -> None:
    # Should not crash on short strings
    score = trigram_similarity("AB", "ABC")
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# label_to_entity_type
# ---------------------------------------------------------------------------


def test_label_organization_maps_to_company() -> None:
    assert label_to_entity_type("organization") == "company"


def test_label_person_maps_to_person() -> None:
    assert label_to_entity_type("person") == "person"


def test_label_unknown_maps_to_topic() -> None:
    assert label_to_entity_type("unknown") == "topic"


# ---------------------------------------------------------------------------
# ResolveEntity — exact match
# ---------------------------------------------------------------------------


def _mention(text: str, label: str = "organization", score: float = 0.9) -> EntityMention:
    return EntityMention(text=text, label=label, score=score)


def _entity(entity_id: str = "e1", name: str = "Tesla, Inc.") -> Entity:
    return Entity(id=entity_id, canonical_name=name, type="company")


@pytest.mark.asyncio
async def test_exact_alias_match_returns_entity() -> None:
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=_entity())
    repo.add_alias = AsyncMock()

    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Tesla"), [])

    assert result.id == "e1"
    repo.add_alias.assert_not_called()


@pytest.mark.asyncio
async def test_exact_match_on_lowercase_adds_alias() -> None:
    # First call (original surface) → None; second call (lowercase) → entity
    entity = _entity()
    repo = MagicMock()
    # "Tesla" → None, "tesla" → entity
    repo.resolve_alias = AsyncMock(side_effect=[None, entity])
    repo.add_alias = AsyncMock()

    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Tesla"), [])

    assert result.id == "e1"
    repo.add_alias.assert_called_once_with("e1", "Tesla")


# ---------------------------------------------------------------------------
# ResolveEntity — fuzzy match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fuzzy_match_links_and_adds_alias() -> None:
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=_entity())
    repo.add_alias = AsyncMock()

    # "Tesla Inc." fuzzy-matches "Tesla Inc" (score well above 0.4)
    candidates = [("Tesla Inc", "e1")]
    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Tesla Inc."), candidates)

    assert result.id == "e1"
    repo.add_alias.assert_called()


@pytest.mark.asyncio
async def test_fuzzy_below_threshold_creates_new() -> None:
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=None)
    repo.save = AsyncMock(side_effect=lambda e: e)
    repo.add_alias = AsyncMock()

    # "Apple" vs "Samsung" — well below threshold
    candidates = [("Samsung Electronics", "e2")]
    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Apple"), candidates)

    assert result.canonical_name == "Apple"
    repo.save.assert_called_once()


# ---------------------------------------------------------------------------
# ResolveEntity — no match → create new
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_match_creates_new_entity() -> None:
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=None)
    repo.save = AsyncMock(side_effect=lambda e: e)
    repo.add_alias = AsyncMock()

    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Anthropic"), [])

    assert result.canonical_name == "Anthropic"
    repo.save.assert_called_once()
    repo.add_alias.assert_called_once()


@pytest.mark.asyncio
async def test_new_entity_type_from_label() -> None:
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=None)
    repo.save = AsyncMock(side_effect=lambda e: e)
    repo.add_alias = AsyncMock()

    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Elon Musk", label="person"), [])

    assert result.type == "person"


@pytest.mark.asyncio
async def test_best_fuzzy_candidate_wins() -> None:
    """When multiple fuzzy candidates exist, the highest-scoring one wins."""
    repo = MagicMock()
    repo.resolve_alias = AsyncMock(return_value=None)

    entity_a = Entity(id="a", canonical_name="Meta Platforms", type="company")
    entity_b = Entity(id="b", canonical_name="Meta Inc.", type="company")

    async def get_by_id_side_effect(entity_id: str) -> Entity:
        return entity_a if entity_id == "a" else entity_b

    repo.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
    repo.add_alias = AsyncMock()

    # "Meta Inc." should score higher against "Meta Inc." than "Meta Platforms"
    candidates = [("Meta Platforms", "a"), ("Meta Inc.", "b")]
    uc = ResolveEntity(repo)
    result = await uc.run(_mention("Meta Inc."), candidates)

    assert result.id == "b"
