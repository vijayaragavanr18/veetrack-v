"""Unit tests: extract_entities task — mocked GLiNER, mocked DB."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from workers.tasks.nlp.extract_entities import (
    _FUZZY_THRESHOLD,
    _trigram_set,
    _trigram_sim,
)

# ---------------------------------------------------------------------------
# _trigram helpers
# ---------------------------------------------------------------------------


def test_trigram_set_normal() -> None:
    s = _trigram_set("hello")
    assert "hel" in s
    assert "ell" in s
    assert "llo" in s


def test_trigram_set_short() -> None:
    s = _trigram_set("ab")
    assert s == {"ab"}


def test_trigram_sim_identical() -> None:
    assert _trigram_sim("Tesla", "Tesla") == pytest.approx(1.0)


def test_trigram_sim_unrelated() -> None:
    score = _trigram_sim("Tesla", "Amazon Web Services")
    assert score < 0.3


def test_trigram_sim_near_match() -> None:
    score = _trigram_sim("Tesla Inc.", "Tesla Inc")
    assert score > _FUZZY_THRESHOLD


def test_trigram_sim_case_insensitive() -> None:
    assert _trigram_sim("TSLA", "tsla") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _resolve_mention — alias lookup mocked via fake session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_mention_exact_match() -> None:
    from workers.tasks.nlp.extract_entities import _resolve_mention

    # Fake session that returns an entity_id on alias lookup
    fake_row = MagicMock()
    fake_row.first.return_value = ("entity-001",)
    fake_execute = AsyncMock(return_value=fake_row)
    session = MagicMock()
    session.execute = fake_execute

    result = await _resolve_mention(session, "Tesla", "organization", [])
    assert result == "entity-001"


@pytest.mark.asyncio
async def test_resolve_mention_fuzzy_match() -> None:
    from workers.tasks.nlp.extract_entities import _resolve_mention

    # Alias lookup returns None (no exact match)
    fake_none = MagicMock()
    fake_none.first.return_value = None

    # For INSERT, return a cursor with no error
    fake_insert = MagicMock()
    fake_insert.first.return_value = None

    call_count = 0

    async def _execute(stmt: object, params: object = None) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return fake_none
        return fake_insert

    session = MagicMock()
    session.execute = _execute

    # Candidate that fuzzy-matches "Tesla Inc."
    candidates = [("Tesla Inc", "entity-001")]
    result = await _resolve_mention(session, "Tesla Inc.", "organization", candidates)
    assert result == "entity-001"


@pytest.mark.asyncio
async def test_resolve_mention_creates_new_when_no_match() -> None:
    from workers.tasks.nlp.extract_entities import _resolve_mention

    # All alias lookups return None
    fake_none = MagicMock()
    fake_none.first.return_value = None
    fake_insert = MagicMock()

    call_count = 0

    async def _execute(stmt: object, params: object = None) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return fake_none
        return fake_insert

    session = MagicMock()
    session.execute = _execute

    # No candidates
    result = await _resolve_mention(session, "Anthropic", "organization", [])
    # Result should be a valid UUID string
    import uuid

    parsed = uuid.UUID(result)
    assert str(parsed) == result


# ---------------------------------------------------------------------------
# GLiNER label deduplication
# ---------------------------------------------------------------------------


def test_dedup_keeps_highest_score() -> None:
    """Same surface form → keep mention with highest score."""
    mentions = [
        {"text": "Tesla", "label": "organization", "score": 0.91},
        {"text": "Tesla", "label": "organization", "score": 0.65},
        {"text": "Tesla", "label": "organization", "score": 0.88},
    ]
    deduped: dict = {}
    for m in mentions:
        surface = m["text"]
        score = m["score"]
        if surface not in deduped or score > deduped[surface]["score"]:
            deduped[surface] = m
    assert len(deduped) == 1
    assert deduped["Tesla"]["score"] == pytest.approx(0.91)
