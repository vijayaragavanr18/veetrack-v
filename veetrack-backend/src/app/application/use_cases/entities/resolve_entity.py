"""Entity resolution use case.

Two-tier strategy (Phase 12 Revised):

FAST PATH — handled deterministically, no LLM:
  1. Exact alias match → return canonical entity.
  2. Normalised lowercase exact match → same.
  3. Fuzzy match with exactly ONE candidate above threshold AND score ≥
     CERTAINTY_THRESHOLD → link to that entity, add alias.

AGENTIC PATH — runs AgentLoop for disambiguation:
  4. Fuzzy match produces MULTIPLE candidates above FUZZY_THRESHOLD,
     OR a single candidate in the gray zone [FUZZY_THRESHOLD, CERTAINTY_THRESHOLD).
  → Agent reads candidate descriptions + article context and either confirms an
    existing entity or creates a new one.

FALLBACK (no gateway or AgentDidNotConvergeError):
  5. Default to creating a new entity rather than guessing a merge.
     A false split is recoverable via nightly reconciliation;
     a false merge silently corrupts two entities' data.

  6. No match at any step → create new canonical entity.

This module contains only pure Python logic + repository calls.
It never imports from infrastructure, fastapi, sqlalchemy, or redis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from app.domain.entities import Entity, EntityType
from app.domain.interfaces.repositories import EntityRepository
from app.domain.interfaces.services import EntityMention

logger = structlog.get_logger(__name__)

FUZZY_THRESHOLD = 0.4
# Above this score with a single candidate → confident match, no agent needed.
CERTAINTY_THRESHOLD = 0.75
_DEFAULT_ENTITY_TYPE: EntityType = "topic"

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

# ToolCallable mirrors shared agent_loop.ToolCallable (kept local to avoid circular import)
ToolCallable = Callable[[dict[str, Any]], Awaitable[str]]


def _normalize(text: str) -> str:
    return text.strip().lower()


def _trigram_set(text: str) -> set[str]:
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
    return _LABEL_TO_TYPE.get(label.lower(), _DEFAULT_ENTITY_TYPE)


@dataclass
class FuzzyMatch:
    entity_id: str
    score: float


def _find_fuzzy_matches(
    surface: str,
    candidate_aliases: list[tuple[str, str]],
    threshold: float,
) -> list[FuzzyMatch]:
    """Return all (entity_id, score) pairs above *threshold*, deduped by entity_id."""
    best: dict[str, float] = {}
    for alias_text, entity_id in candidate_aliases:
        score = trigram_similarity(surface, alias_text)
        if score >= threshold and score > best.get(entity_id, 0.0):
            best[entity_id] = score
    return sorted(
        [FuzzyMatch(entity_id=eid, score=s) for eid, s in best.items()],
        key=lambda m: m.score,
        reverse=True,
    )


def is_ambiguous(matches: list[FuzzyMatch], certainty_threshold: float) -> bool:
    """Return True when the match set warrants the agentic path.

    Ambiguous when:
    - Multiple candidates above FUZZY_THRESHOLD, OR
    - Exactly one candidate but score is in the gray zone
      [FUZZY_THRESHOLD, certainty_threshold).
    """
    if not matches:
        return False
    if len(matches) > 1:
        return True
    return matches[0].score < certainty_threshold


class ResolveEntity:
    """Resolve a raw entity mention to a canonical Entity, creating one if needed.

    Parameters
    ----------
    entity_repo:
        Repository providing alias lookup and entity persistence.
    fuzzy_threshold:
        Minimum trigram Jaccard similarity to accept a fuzzy match.
    certainty_threshold:
        Single-candidate score above which the fast path resolves without LLM.
    gateway:
        LLMGateway for the agentic path.  Pass None to disable (falls straight
        to new-entity creation on any ambiguous case).
    tools:
        Dict of tool_name → async callable injected into the agentic loop.
    system_prompt:
        Override for the agent system prompt (mainly for tests).
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
        certainty_threshold: float = CERTAINTY_THRESHOLD,
        gateway: Any | None = None,
        tools: dict[str, ToolCallable] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._repo = entity_repo
        self._fuzzy_threshold = fuzzy_threshold
        self._certainty_threshold = certainty_threshold
        self._gateway = gateway
        self._tools: dict[str, ToolCallable] = tools or {}
        self._system_prompt = system_prompt

    async def run(
        self,
        mention: EntityMention,
        candidate_aliases: list[tuple[str, str]],
        article_id: str = "",
    ) -> Entity:
        """Resolve *mention* to a canonical Entity.

        Parameters
        ----------
        mention:
            The raw entity mention from NER.
        candidate_aliases:
            List of (alias_text, entity_id) tuples from the DB for fuzzy
            comparison.  Should be pre-fetched by the caller to avoid N+1 queries.
        article_id:
            The article containing the mention; passed to agentic tools for context.
        """
        surface = mention.text.strip()

        # 1. Exact alias match
        exact = await self._repo.resolve_alias(surface)
        if exact is not None:
            logger.debug("entity.resolved_exact", surface=surface, entity_id=exact.id)
            return exact

        # 2. Normalised lowercase exact match
        if surface != _normalize(surface):
            exact_lower = await self._repo.resolve_alias(_normalize(surface))
            if exact_lower is not None:
                await self._add_alias(exact_lower.id, surface)
                return exact_lower

        # 3. Fuzzy matching
        matches = _find_fuzzy_matches(surface, candidate_aliases, self._fuzzy_threshold)

        if not matches:
            # No candidates — create new entity
            return await self._create_new(surface, mention.label)

        if not is_ambiguous(matches, self._certainty_threshold):
            # Single clear match above certainty threshold → fast path
            entity = await self._repo.get_by_id(matches[0].entity_id)
            await self._add_alias(entity.id, surface)
            logger.debug(
                "entity.resolved_fuzzy",
                surface=surface,
                entity_id=entity.id,
                score=matches[0].score,
            )
            return entity

        # 4. Ambiguous — try agentic path
        if self._gateway is not None:
            resolved = await self._run_agentic(surface, mention, article_id, matches)
            if resolved is not None:
                return resolved

        # 5. Fallback: create new entity rather than guess a merge
        logger.info(
            "entity.resolution_fallback_new",
            surface=surface,
            candidates=[m.entity_id for m in matches],
        )
        return await self._create_new(surface, mention.label)

    async def _run_agentic(
        self,
        surface: str,
        mention: EntityMention,
        article_id: str,
        matches: list[FuzzyMatch],
    ) -> Entity | None:
        """Run the AgentLoop to disambiguate *surface*.

        Returns the resolved Entity, or None if the agent says it's new
        (caller will then create a new entity).
        """
        from app.application.use_cases.entities.prompts.agentic_entity_resolution import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )
        from app.application.use_cases.shared.agent_loop import (
            AgentDidNotConvergeError,
            AgentLoop,
        )

        system = self._system_prompt or SYSTEM_PROMPT
        loop = AgentLoop(
            gateway=self._gateway,
            system_prompt=system,
            tool_names=TOOL_NAMES,
            tools=self._tools,
            max_iterations=6,
            max_tokens_per_step=600,
            agent_name="entity_agent",
        )

        candidate_summary = ", ".join(
            f"{m.entity_id!r}(sim={m.score:.2f})" for m in matches[:5]
        )
        initial_msg = (
            f"Entity mention: {surface!r}\n"
            f"Article ID: {article_id!r}\n"
            f"Mention offset: {mention.start}\n"
            f"GLiNER label: {mention.label!r}\n"
            f"Fuzzy candidates: [{candidate_summary}]\n\n"
            "Determine whether this mention refers to an existing canonical entity "
            "or is a genuinely new one.  Use the available tools to inspect candidates "
            "and article context, then produce a final_answer."
        )

        try:
            loop_result = await loop.run(
                initial_msg, run_id=f"entity:{surface}:{article_id}"
            )
        except AgentDidNotConvergeError:
            logger.warning(
                "entity.agent_did_not_converge",
                surface=surface,
                article_id=article_id,
                candidates=[m.entity_id for m in matches],
            )
            return None  # fallback → new entity

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning(
                "entity.invalid_final_answer",
                surface=surface,
                error=str(ve),
            )
            return None  # fallback → new entity

        if final["resolution"] == "new":
            logger.info(
                "entity.agentic_new",
                surface=surface,
                reasoning=final.get("reasoning", "")[:100],
            )
            return None  # caller creates new entity

        # resolution == "existing"
        entity_id = final["entity_id"]
        try:
            entity = await self._repo.get_by_id(entity_id)
            await self._add_alias(entity.id, surface)
            logger.info(
                "entity.agentic_resolved",
                surface=surface,
                entity_id=entity_id,
                reasoning=final.get("reasoning", "")[:100],
            )
            return entity
        except Exception as exc:
            logger.warning(
                "entity.agentic_entity_not_found",
                surface=surface,
                entity_id=entity_id,
                error=str(exc),
            )
            return None  # fallback → new entity

    async def _add_alias(self, entity_id: str, alias_text: str) -> None:
        await self._repo.add_alias(entity_id, alias_text)

    async def _create_new(self, surface: str, label: str) -> Entity:
        entity = Entity(
            id=str(uuid.uuid4()),
            canonical_name=surface,
            type=label_to_entity_type(label),
        )
        entity = await self._repo.save(entity)
        await self._repo.add_alias(entity.id, surface)
        logger.info("entity.created", surface=surface, entity_id=entity.id)
        return entity
