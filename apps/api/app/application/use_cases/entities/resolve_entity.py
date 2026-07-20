"""Entity resolution use case.

Strategy (alias-lookup-first):
  1. Exact alias match  → return the canonical entity.
  2. Fuzzy alias match above threshold (trigram Jaccard ≥ FUZZY_THRESHOLD)
     → link to the best-scoring existing entity, add the surface form as a
     new alias so future lookups are exact.
  3. No match → create a new canonical entity + seed alias.

This module contains only pure Python logic + repository calls.
It never imports from infrastructure, fastapi, sqlalchemy, or redis.
"""

from __future__ import annotations

import uuid

import structlog

from app.domain.entities import Entity, EntityType
from app.domain.interfaces.repositories import EntityRepository
from app.domain.interfaces.services import EntityMention

logger = structlog.get_logger(__name__)

FUZZY_THRESHOLD = 0.4
_DEFAULT_ENTITY_TYPE: EntityType = "topic"

# Map GLiNER label strings to our EntityType literals
_LABEL_TO_TYPE: dict[str, EntityType] = {
    "organization": "company",
    "org": "company",
    "company": "company",
    "person": "person",
    "per": "person",
    "location": "topic",
    "loc": "topic",
    "topic": "topic",
}


def _normalize(text: str) -> str:
    """Lower-case + strip for case-insensitive matching."""
    return text.strip().lower()


def _trigram_set(text: str) -> set[str]:
    """Return character 3-gram set for Jaccard similarity."""
    s = _normalize(text)
    if len(s) < 3:
        return {s}
    return {s[i : i + 3] for i in range(len(s) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """Jaccard similarity on character 3-grams (case-insensitive)."""
    ta, tb = _trigram_set(a), _trigram_set(b)
    if not ta and not tb:
        return 1.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


def label_to_entity_type(label: str) -> EntityType:
    """Convert a GLiNER label string to our EntityType."""
    return _LABEL_TO_TYPE.get(label.lower(), _DEFAULT_ENTITY_TYPE)


class ResolveEntity:
    """Resolve a raw entity mention to a canonical Entity, creating one if needed.

    Parameters
    ----------
    entity_repo:
        Repository providing alias lookup and entity persistence.
    fuzzy_threshold:
        Minimum trigram Jaccard similarity to accept a fuzzy match.
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
    ) -> None:
        self._repo = entity_repo
        self._fuzzy_threshold = fuzzy_threshold

    async def run(
        self,
        mention: EntityMention,
        candidate_aliases: list[tuple[str, str]],
    ) -> Entity:
        """Resolve *mention* to a canonical Entity.

        Parameters
        ----------
        mention:
            The raw entity mention from NER.
        candidate_aliases:
            List of (alias_text, entity_id) tuples from the DB for fuzzy
            comparison.  Should be pre-fetched by the caller to avoid N+1
            queries.

        Returns the resolved (or newly created) Entity.
        """
        surface = mention.text.strip()

        # 1. Exact alias match
        exact = await self._repo.resolve_alias(surface)
        if exact is not None:
            logger.debug(
                "entity.resolved_exact",
                surface=surface,
                entity_id=exact.id,
                canonical=exact.canonical_name,
            )
            return exact

        # Also try normalised lowercase
        if surface != _normalize(surface):
            exact_lower = await self._repo.resolve_alias(_normalize(surface))
            if exact_lower is not None:
                await self._add_alias(exact_lower.id, surface)
                return exact_lower

        # 2. Fuzzy match against candidate aliases
        best_entity_id: str | None = None
        best_score = 0.0
        for alias_text, entity_id in candidate_aliases:
            score = trigram_similarity(surface, alias_text)
            if score >= self._fuzzy_threshold and score > best_score:
                best_score = score
                best_entity_id = entity_id

        if best_entity_id is not None:
            entity = await self._repo.get_by_id(best_entity_id)
            await self._add_alias(entity.id, surface)
            logger.debug(
                "entity.resolved_fuzzy",
                surface=surface,
                entity_id=entity.id,
                score=best_score,
            )
            return entity

        # 3. No match — create new canonical entity
        entity = await self._create_new(surface, mention.label)
        logger.info(
            "entity.created",
            surface=surface,
            entity_id=entity.id,
            canonical=entity.canonical_name,
        )
        return entity

    async def _add_alias(self, entity_id: str, alias_text: str) -> None:
        """Add a new alias for an existing entity (best-effort)."""
        await self._repo.add_alias(entity_id, alias_text)

    async def _create_new(self, surface: str, label: str) -> Entity:
        entity = Entity(
            id=str(uuid.uuid4()),
            canonical_name=surface,
            type=label_to_entity_type(label),
        )
        entity = await self._repo.save(entity)
        await self._repo.add_alias(entity.id, surface)
        return entity
