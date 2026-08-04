"""Unit tests for the agentic entity resolution agent (Phase 12 revised).

Tests cover:
  - is_ambiguous: single clear match, single gray-zone, multiple candidates.
  - _find_fuzzy_matches: dedup by entity_id, score ordering.
  - ResolveEntity fast path: exact, lowercase exact, clear single fuzzy match.
  - ResolveEntity agentic path: multiple candidates → agent called.
  - ResolveEntity agentic path: single gray-zone candidate → agent called.
  - Agentic resolution=existing → entity fetched and alias added.
  - Agentic resolution=new → new entity created.
  - Fallback: no gateway → new entity created on ambiguous case.
  - Fallback: agent non-convergence → new entity created.
  - Fallback: invalid final answer → new entity created.
  - Tool functions against fakes.
  - validate_final_answer: valid and invalid shapes.
  - Architecture: prompt and use case have no infra imports.

No infrastructure imports. All I/O via fakes.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.use_cases.entities.prompts.agentic_entity_resolution import (
    validate_final_answer,
)
from app.application.use_cases.entities.resolve_entity import (
    CERTAINTY_THRESHOLD,
    FUZZY_THRESHOLD,
    ResolveEntity,
    _find_fuzzy_matches,
    is_ambiguous,
    trigram_similarity,
)
from app.application.use_cases.shared.agent_loop import AgentDidNotConvergeError
from app.domain.entities import Entity
from app.domain.interfaces.services import EntityMention

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mention(
    text: str,
    label: str = "organization",
    score: float = 0.9,
    start: int = 0,
    end: int = 0,
) -> EntityMention:
    return EntityMention(text=text, label=label, score=score, start=start, end=end)


def _entity(entity_id: str = "e1", name: str = "Apple Inc.", etype: str = "company") -> Entity:
    return Entity(id=entity_id, canonical_name=name, type=etype)  # type: ignore[arg-type]


class FakeGateway:
    model_name: str = "fake-model"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        if not self._responses:
            raise ValueError("FakeGateway: no more responses")
        return self._responses.pop(0)

    async def complete_json(
        self, prompt: str, schema: dict[str, Any], *, system: str = "", max_tokens: int = 2048
    ) -> dict[str, Any]:
        raw = await self.complete(prompt, system=system, max_tokens=max_tokens)
        return json.loads(raw)


def _final_existing(entity_id: str = "e1") -> str:
    return json.dumps({
        "type": "final_answer",
        "resolution": "existing",
        "entity_id": entity_id,
        "reasoning": "Article context confirms this is Apple Inc. (company context: CEO, iPhone).",
    })


def _final_new() -> str:
    return json.dumps({
        "type": "final_answer",
        "resolution": "new",
        "entity_id": None,
        "reasoning": "Context is about an orchard, not a tech company.",
    })


# ── Unit: is_ambiguous ────────────────────────────────────────────────────────


class TestIsAmbiguous:
    def test_no_matches_not_ambiguous(self) -> None:
        assert is_ambiguous([], CERTAINTY_THRESHOLD) is False

    def test_single_match_above_certainty_not_ambiguous(self) -> None:
        from app.application.use_cases.entities.resolve_entity import FuzzyMatch
        matches = [FuzzyMatch(entity_id="e1", score=0.9)]
        assert is_ambiguous(matches, CERTAINTY_THRESHOLD) is False

    def test_single_match_at_certainty_not_ambiguous(self) -> None:
        from app.application.use_cases.entities.resolve_entity import FuzzyMatch
        matches = [FuzzyMatch(entity_id="e1", score=CERTAINTY_THRESHOLD)]
        assert is_ambiguous(matches, CERTAINTY_THRESHOLD) is False

    def test_single_match_in_gray_zone_is_ambiguous(self) -> None:
        from app.application.use_cases.entities.resolve_entity import FuzzyMatch
        gray = (FUZZY_THRESHOLD + CERTAINTY_THRESHOLD) / 2
        matches = [FuzzyMatch(entity_id="e1", score=gray)]
        assert is_ambiguous(matches, CERTAINTY_THRESHOLD) is True

    def test_multiple_matches_is_ambiguous(self) -> None:
        from app.application.use_cases.entities.resolve_entity import FuzzyMatch
        matches = [
            FuzzyMatch(entity_id="e1", score=0.8),
            FuzzyMatch(entity_id="e2", score=0.6),
        ]
        assert is_ambiguous(matches, CERTAINTY_THRESHOLD) is True


# ── Unit: _find_fuzzy_matches ─────────────────────────────────────────────────


class TestFindFuzzyMatches:
    def test_empty_candidates(self) -> None:
        assert _find_fuzzy_matches("Tesla", [], FUZZY_THRESHOLD) == []

    def test_deduplicates_by_entity_id_keeps_best(self) -> None:
        # "Amazon" vs two aliases of the same entity — keep higher score
        candidates = [
            ("Amazon.com", "e1"),     # sim ≈ 0.5
            ("Amazonia", "e1"),       # sim ≈ 0.667
        ]
        matches = _find_fuzzy_matches("Amazon", candidates, FUZZY_THRESHOLD)
        assert len(matches) == 1
        assert matches[0].entity_id == "e1"
        assert matches[0].score == pytest.approx(
            trigram_similarity("Amazon", "Amazonia"), abs=0.01
        )

    def test_multiple_entities_above_threshold(self) -> None:
        # "Amazon" matches both Amazon.com (co) and Amazonia (topic)
        candidates = [
            ("Amazon.com", "e-amazon"),
            ("Amazonia", "e-amazonia"),
        ]
        matches = _find_fuzzy_matches("Amazon", candidates, FUZZY_THRESHOLD)
        assert len(matches) == 2

    def test_sorted_by_score_descending(self) -> None:
        candidates = [
            ("Amazon.com", "e1"),
            ("Amazonia", "e2"),
        ]
        matches = _find_fuzzy_matches("Amazon", candidates, FUZZY_THRESHOLD)
        assert matches[0].score >= matches[1].score

    def test_below_threshold_excluded(self) -> None:
        # "Apple" only clears threshold when alias is close enough
        candidates = [("Completely Unrelated Company Name", "e1")]
        matches = _find_fuzzy_matches("Apple", candidates, FUZZY_THRESHOLD)
        assert matches == []


# ── Unit: ResolveEntity fast path ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestResolveEntityFastPath:
    async def test_exact_alias_no_llm(self) -> None:
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=_entity())
        repo.add_alias = AsyncMock()
        uc = ResolveEntity(repo)
        result = await uc.run(_mention("Apple"), [])
        assert result.id == "e1"
        repo.add_alias.assert_not_called()

    async def test_lowercase_exact_adds_alias(self) -> None:
        entity = _entity()
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(side_effect=[None, entity])
        repo.add_alias = AsyncMock()
        uc = ResolveEntity(repo)
        result = await uc.run(_mention("APPLE INC."), [])
        assert result.id == "e1"
        repo.add_alias.assert_called_once()

    async def test_clear_single_fuzzy_match_no_llm(self) -> None:
        # "Apple Inc" vs "Apple Inc." scores 0.875 — above CERTAINTY_THRESHOLD
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(return_value=_entity())
        repo.add_alias = AsyncMock()
        candidates = [("Apple Inc.", "e1")]
        uc = ResolveEntity(repo)
        result = await uc.run(_mention("Apple Inc"), candidates)
        assert result.id == "e1"

    async def test_no_candidates_creates_new(self) -> None:
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()
        uc = ResolveEntity(repo)
        result = await uc.run(_mention("BrandNewCorp"), [])
        assert result.canonical_name == "BrandNewCorp"
        repo.save.assert_called_once()


# ── Unit: ResolveEntity agentic path ─────────────────────────────────────────


@pytest.mark.asyncio
class TestResolveEntityAgenticPath:
    async def test_multiple_candidates_triggers_agentic(self) -> None:
        """Two Amazon candidates above threshold → agent called."""
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(return_value=_entity("e-amazon", "Amazon.com"))
        repo.add_alias = AsyncMock()

        # "Amazon" fuzzy-matches both Amazon.com and Amazonia
        candidates = [
            ("Amazon.com", "e-amazon"),
            ("Amazonia", "e-amazonia"),
        ]
        gateway = FakeGateway(responses=[_final_existing("e-amazon")])
        uc = ResolveEntity(repo, gateway=gateway)
        result = await uc.run(_mention("Amazon"), candidates, article_id="art-1")

        assert result.id == "e-amazon"
        repo.add_alias.assert_called()

    async def test_gray_zone_single_candidate_triggers_agentic(self) -> None:
        """Single candidate in gray zone [0.4, 0.75) → agent called."""
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(return_value=_entity("e-amazon", "Amazon.com"))
        repo.add_alias = AsyncMock()

        # Amazon vs Amazon.com scores ~0.5 (gray zone)
        candidates = [("Amazon.com", "e-amazon")]
        gateway = FakeGateway(responses=[_final_existing("e-amazon")])
        uc = ResolveEntity(repo, gateway=gateway)
        result = await uc.run(_mention("Amazon"), candidates, article_id="art-1")

        assert result.id == "e-amazon"

    async def test_agentic_resolution_new_creates_entity(self) -> None:
        """Agent decides it's new → new entity created."""
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()

        candidates = [("Amazon.com", "e-amazon"), ("Amazonia", "e-amazonia")]
        gateway = FakeGateway(responses=[_final_new()])
        uc = ResolveEntity(repo, gateway=gateway)
        result = await uc.run(_mention("Amazon", label="location"), candidates, "art-1")

        # Agent said "new" → creates fresh entity
        assert result.canonical_name == "Amazon"
        repo.save.assert_called_once()

    async def test_no_gateway_ambiguous_creates_new(self) -> None:
        """No gateway + ambiguous case → safe fallback to new entity."""
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()

        candidates = [("Amazon.com", "e1"), ("Amazonia", "e2")]
        uc = ResolveEntity(repo, gateway=None)
        result = await uc.run(_mention("Amazon"), candidates)

        assert result.canonical_name == "Amazon"
        repo.save.assert_called_once()

    async def test_agent_non_convergence_creates_new(self) -> None:
        """AgentDidNotConvergeError → safe fallback to new entity.

        The AgentLoop is imported inside _run_agentic(), so we patch the class
        at its definition module and provide a mock instance whose .run() raises.
        """
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()

        candidates = [("Amazon.com", "e1"), ("Amazonia", "e2")]

        # Patch AgentLoop where it is defined so the deferred import picks it up.
        with patch(
            "app.application.use_cases.shared.agent_loop.AgentLoop",
            autospec=True,
        ) as MockLoopCls:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(
                side_effect=AgentDidNotConvergeError("no convergence")
            )
            MockLoopCls.return_value = mock_instance

            gateway = FakeGateway(responses=[])
            uc = ResolveEntity(repo, gateway=gateway)
            result = await uc.run(_mention("Amazon"), candidates, "art-1")

        assert result.canonical_name == "Amazon"
        repo.save.assert_called_once()

    async def test_invalid_final_answer_creates_new(self) -> None:
        """Invalid agent answer → safe fallback to new entity."""
        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()

        bad_response = json.dumps({
            "type": "final_answer",
            "resolution": "maybe",
            "entity_id": None,
            "reasoning": "unsure",
        })
        candidates = [("Amazon.com", "e1"), ("Amazonia", "e2")]
        gateway = FakeGateway(responses=[bad_response])
        uc = ResolveEntity(repo, gateway=gateway)
        result = await uc.run(_mention("Amazon"), candidates, "art-1")

        assert result.canonical_name == "Amazon"
        repo.save.assert_called_once()

    async def test_agentic_entity_not_found_in_repo_creates_new(self) -> None:
        """Agent says existing but entity_id not in DB → create new (defensive)."""
        from app.domain.exceptions import NotFoundError

        repo = MagicMock()
        repo.resolve_alias = AsyncMock(return_value=None)
        repo.get_by_id = AsyncMock(side_effect=NotFoundError("not found"))
        repo.save = AsyncMock(side_effect=lambda e: e)
        repo.add_alias = AsyncMock()

        candidates = [("Amazon.com", "e-bad-id"), ("Amazonia", "e2")]
        gateway = FakeGateway(responses=[_final_existing("e-bad-id")])
        uc = ResolveEntity(repo, gateway=gateway)
        result = await uc.run(_mention("Amazon"), candidates, "art-1")

        assert result.canonical_name == "Amazon"
        repo.save.assert_called_once()


# ── Unit: validate_final_answer ───────────────────────────────────────────────


class TestValidateFinalAnswer:
    def test_valid_existing(self) -> None:
        validate_final_answer({
            "type": "final_answer",
            "resolution": "existing",
            "entity_id": "ent-123",
            "reasoning": "Context confirms Apple Inc.",
        })

    def test_valid_new(self) -> None:
        validate_final_answer({
            "type": "final_answer",
            "resolution": "new",
            "entity_id": None,
            "reasoning": "Context is about an orchard.",
        })

    def test_wrong_type(self) -> None:
        with pytest.raises(ValueError, match='Expected type="final_answer"'):
            validate_final_answer({
                "type": "tool_call",
                "resolution": "new",
                "entity_id": None,
                "reasoning": "x",
            })

    def test_invalid_resolution(self) -> None:
        with pytest.raises(ValueError, match="Invalid resolution"):
            validate_final_answer({
                "type": "final_answer",
                "resolution": "maybe",
                "entity_id": None,
                "reasoning": "x",
            })

    def test_existing_without_entity_id(self) -> None:
        with pytest.raises(ValueError, match="entity_id.*must be set"):
            validate_final_answer({
                "type": "final_answer",
                "resolution": "existing",
                "entity_id": None,
                "reasoning": "Apple Inc.",
            })

    def test_new_with_entity_id_set(self) -> None:
        with pytest.raises(ValueError, match="entity_id.*must be null"):
            validate_final_answer({
                "type": "final_answer",
                "resolution": "new",
                "entity_id": "some-id",
                "reasoning": "x",
            })

    def test_missing_reasoning(self) -> None:
        with pytest.raises(ValueError, match='"reasoning"'):
            validate_final_answer({
                "type": "final_answer",
                "resolution": "new",
                "entity_id": None,
                "reasoning": "",
            })


# ── Unit: tool functions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetCandidateEntities:
    async def test_empty_alias_text(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_entities import get_candidate_entities

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_candidate_entities({"alias_text": ""}, _q)
        assert "required" in result.lower() or "alias_text" in result

    async def test_no_candidates(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_entities import get_candidate_entities

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_candidate_entities({"alias_text": "BrandNewOrg"}, _q)
        assert "no candidate" in result.lower() or "new entity" in result.lower()

    async def test_returns_matching_candidates(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_entities import get_candidate_entities

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {
                    "alias": "Amazon.com",
                    "entity_id": "e-amazon",
                    "canonical_name": "Amazon.com, Inc.",
                    "entity_type": "company",
                    "description": "US e-commerce and cloud company",
                },
                {
                    "alias": "Amazonia",
                    "entity_id": "e-amazonia",
                    "canonical_name": "Amazonia",
                    "entity_type": "topic",
                    "description": "Amazon rainforest region in South America",
                },
            ]

        result = await get_candidate_entities({"alias_text": "Amazon"}, _q)
        assert "Amazon.com, Inc." in result or "e-amazon" in result

    async def test_caps_at_ten_candidates(self) -> None:
        from app.infrastructure.llm.tools.get_candidate_entities import get_candidate_entities

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                {
                    "alias": f"Amazon{i}",
                    "entity_id": f"e-{i}",
                    "canonical_name": f"Entity {i}",
                    "entity_type": "topic",
                    "description": "",
                }
                for i in range(15)
            ]

        result = await get_candidate_entities({"alias_text": "Amazon"}, _q)
        # Should mention "more" for the overflow
        assert "more" in result.lower() or result.count("entity_id") <= 10


@pytest.mark.asyncio
class TestGetArticleContext:
    async def test_not_found(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import get_article_context

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return []

        result = await get_article_context({"article_id": "missing"}, _q)
        assert "no article" in result.lower() or "missing" in result

    async def test_returns_headline(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import get_article_context

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{
                "headline": "Apple CEO Tim Cook announces record profits",
                "clean_content": "Apple Inc reported record profits in Q4.",
            }]

        result = await get_article_context({"article_id": "art-1", "mention_offset": 0}, _q)
        assert "Apple CEO Tim Cook" in result

    async def test_context_window_centered_on_offset(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import (
            get_article_context,
        )

        content = "x" * 500 + "MENTION_HERE" + "y" * 500

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"headline": "Test", "clean_content": content}]

        result = await get_article_context(
            {"article_id": "art-1", "mention_offset": 500}, _q
        )
        assert "MENTION_HERE" in result

    async def test_no_content_falls_back_to_headline(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import get_article_context

        async def _q(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            return [{"headline": "Apple Orchard Festival", "clean_content": ""}]

        result = await get_article_context({"article_id": "art-1"}, _q)
        assert "Apple Orchard Festival" in result
        assert "headline" in result.lower()


# ── Unit: _extract_context helper ─────────────────────────────────────────────


class TestExtractContext:
    def test_offset_zero_returns_start(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import _extract_context

        text = "Apple Inc CEO announces record Q4 profits."
        ctx = _extract_context(text, 0)
        assert "Apple Inc" in ctx

    def test_offset_in_middle(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import _extract_context

        text = "start " + "Apple" + " CEO Tim Cook end"
        ctx = _extract_context(text, 6, window=20)
        assert "Apple" in ctx

    def test_long_text_adds_ellipsis(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import _extract_context

        text = "a" * 1000 + "TARGET" + "b" * 1000
        ctx = _extract_context(text, 1000, window=50)
        assert "TARGET" in ctx
        assert "…" in ctx

    def test_empty_text(self) -> None:
        from app.infrastructure.llm.tools.get_article_context import _extract_context

        assert _extract_context("", 0) == ""


# ── Architecture checks ───────────────────────────────────────────────────────


class TestArchitecture:
    def test_entity_resolution_prompt_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/entities/prompts/agentic_entity_resolution.py"
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
                            f"entity resolution prompt imports {name!r} (infra violation)"
                        )

    def test_resolve_entity_has_no_infra_imports(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(
            "src/app/application/use_cases/entities/resolve_entity.py"
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
                            f"resolve_entity imports {name!r} (infra violation)"
                        )
