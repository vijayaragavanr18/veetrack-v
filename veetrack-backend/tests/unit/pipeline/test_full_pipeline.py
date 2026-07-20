"""Phase 28 — Full pipeline integration test (in-memory fakes).

Exercises the sequential pipeline stages end-to-end without any infrastructure:
  normalize → dedup → entity resolve → embed → cluster assign → feed cache

All I/O is via in-memory fakes; no DB, Redis, or model loading required.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

import pytest

from app.application.use_cases.clustering.assign_to_story import (
    AssignToStory,
    AssignmentResult,
    cosine_similarity,
    update_centroid,
)
from app.application.use_cases.embeddings.embed_article import EmbedArticle, EmbedResult
from app.application.use_cases.entities.resolve_entity import (
    ResolveEntity,
    trigram_similarity,
)
from app.application.use_cases.pipeline.deduplicate import (
    add_to_index,
    build_lsh_index,
    compute_minhash,
    find_duplicate,
    is_near_duplicate,
)
from app.application.use_cases.pipeline.normalize import (
    clean_whitespace,
    normalize_article,
    strip_html,
)
from app.application.use_cases.search.feed_types import (
    ArticleSummaryItem,
    StoryPayload,
    feed_cache_key,
)
from app.application.use_cases.search.get_feed import (
    GetFeed,
    _deserialise_payloads,
    serialise_payloads,
)
from app.domain.entities import Entity, EntityType
from app.domain.interfaces.services import EntityMention

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeEmbeddingService:
    EMBEDDING_DIM = 4

    def embed(self, text: str) -> list[float]:
        # Deterministic 4-dim vector based on text length, L2-normalised
        raw = [float(len(text) % 4 + 1), 1.0, 0.5, 0.25]
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class _FakeEntityRepository:
    """In-memory entity + alias store."""

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._aliases: dict[str, str] = {}  # alias_text.lower() → entity_id

    async def resolve_alias(self, alias_text: str) -> Entity | None:
        eid = self._aliases.get(alias_text.lower())
        if eid is None:
            return None
        return self._entities.get(eid)

    async def get_by_id(self, entity_id: str) -> Entity:
        entity = self._entities[entity_id]
        return entity

    async def save(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity
        return entity

    async def add_alias(self, entity_id: str, alias_text: str) -> None:
        self._aliases[alias_text.lower()] = entity_id

    def seed(self, entity: Entity, aliases: list[str]) -> None:
        self._entities[entity.id] = entity
        for alias in aliases:
            self._aliases[alias.lower()] = entity.id


class _FakeCache:
    def __init__(self, initial: dict[str, bytes] | None = None) -> None:
        self._data: dict[str, bytes] = initial or {}

    async def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int = 300) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def ping(self) -> bool:
        return True


class _FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, task_name: str, *, args: tuple[Any, ...] = (), kwargs: dict[str, Any] | None = None, queue: str | None = None) -> str:
        self.calls.append({"task": task_name, "kwargs": kwargs, "queue": queue})
        return str(uuid.uuid4())


def _make_db_stub(
    entity_rows: list[dict] | None = None,
    story_rows: list[dict] | None = None,
) -> Any:
    async def _stub(sql: str, params: dict[str, Any]) -> list[dict]:
        if "entity_aliases" in sql:
            return entity_rows or []
        if "stories" in sql:
            return story_rows or []
        if "ANY(:sids)" in sql:
            return []
        return []
    return _stub


def _unit_vec(dim: int, idx: int) -> list[float]:
    """Return a unit vector with 1.0 at position idx, 0 elsewhere."""
    v = [0.0] * dim
    v[idx % dim] = 1.0
    return v


# ---------------------------------------------------------------------------
# 1. Normalize — strip_html
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags() -> None:
    result = strip_html("<p>Hello <b>world</b>!</p>")
    assert "<" not in result
    assert "Hello" in result
    assert "world" in result


def test_strip_html_nested_divs() -> None:
    result = strip_html("<div><h1>Title</h1><p>Body text here.</p></div>")
    assert "Title" in result
    assert "Body text here." in result
    assert "<" not in result


def test_clean_whitespace_collapses_spaces() -> None:
    result = clean_whitespace("  Hello   world  \n\n\n  foo  ")
    assert "  " not in result
    assert "Hello world" in result


def test_normalize_article_returns_tuple() -> None:
    html = "<p>Tesla reported strong Q2 earnings today.</p>"
    clean, lang = normalize_article(html)
    assert "Tesla" in clean
    assert "<" not in clean
    assert isinstance(lang, str)
    assert len(lang) >= 2  # BCP-47 code


# ---------------------------------------------------------------------------
# 2. Dedup — MinHash/LSH
# ---------------------------------------------------------------------------

def test_near_duplicate_identical_text() -> None:
    text = "This is a test article about Tesla's earnings."
    assert is_near_duplicate(text, text) is True


def test_near_duplicate_different_text() -> None:
    text_a = "Tesla reports record Q2 profit of ten billion dollars."
    text_b = "Apple unveils new iPhone with satellite connectivity features."
    # Very different content — should not be near-duplicates
    assert is_near_duplicate(text_a, text_b) is False


def test_lsh_index_finds_duplicate() -> None:
    lsh = build_lsh_index()
    text = "Tesla reports record earnings for the quarter."
    mh = compute_minhash(text)
    add_to_index(lsh, "article-1", mh)
    # Slightly modified version — still near-duplicate
    mh2 = compute_minhash(text + " strong results.")
    result = find_duplicate(lsh, mh2)
    assert result == "article-1"


def test_lsh_index_no_duplicate_for_unrelated_text() -> None:
    lsh = build_lsh_index()
    mh = compute_minhash("Tesla Q2 earnings report results.")
    add_to_index(lsh, "article-1", mh)
    mh2 = compute_minhash("Apple unveils satellite phone.")
    result = find_duplicate(lsh, mh2)
    assert result is None


# ---------------------------------------------------------------------------
# 3. Entity resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entity_resolve_exact_match() -> None:
    repo = _FakeEntityRepository()
    entity = Entity(id="eid-1", canonical_name="Tesla, Inc.", type="company")
    repo.seed(entity, ["Tesla", "tesla", "$tsla"])

    resolver = ResolveEntity(entity_repo=repo)
    mention = EntityMention(text="Tesla", label="organization", score=0.9)
    result = await resolver.run(mention, candidate_aliases=[])

    assert result.id == "eid-1"
    assert result.canonical_name == "Tesla, Inc."


@pytest.mark.asyncio
async def test_entity_resolve_creates_new_when_no_match() -> None:
    repo = _FakeEntityRepository()
    resolver = ResolveEntity(entity_repo=repo)
    mention = EntityMention(text="Completely New Corp", label="organization", score=0.95)
    result = await resolver.run(mention, candidate_aliases=[])

    assert result.canonical_name == "Completely New Corp"
    # Should now be findable by alias
    found = await repo.resolve_alias("Completely New Corp")
    assert found is not None
    assert found.id == result.id


@pytest.mark.asyncio
async def test_entity_resolve_fuzzy_match() -> None:
    repo = _FakeEntityRepository()
    entity = Entity(id="eid-2", canonical_name="Microsoft Corporation", type="company")
    repo.seed(entity, ["Microsoft"])

    resolver = ResolveEntity(entity_repo=repo)
    mention = EntityMention(text="Microsft", label="organization", score=0.8)
    # Provide the alias for fuzzy comparison
    result = await resolver.run(mention, candidate_aliases=[("Microsoft", "eid-2")])

    assert result.id == "eid-2"


def test_trigram_similarity_identical() -> None:
    assert trigram_similarity("Tesla", "Tesla") == pytest.approx(1.0)


def test_trigram_similarity_unrelated() -> None:
    score = trigram_similarity("Tesla", "Zurich")
    assert score < 0.3


# ---------------------------------------------------------------------------
# 4. Embed article
# ---------------------------------------------------------------------------

def test_embed_article_returns_non_zero_vector() -> None:
    service = _FakeEmbeddingService()
    use_case = EmbedArticle(service=service)
    result = use_case.run("Tesla reports record earnings this quarter.")
    assert result.skipped is False
    assert len(result.vector) == 4
    assert any(v != 0.0 for v in result.vector)


def test_embed_article_empty_content_returns_skipped() -> None:
    service = _FakeEmbeddingService()
    use_case = EmbedArticle(service=service)
    result = use_case.run("")
    assert result.skipped is True
    assert all(v == 0.0 for v in result.vector)


def test_embed_article_batch() -> None:
    service = _FakeEmbeddingService()
    use_case = EmbedArticle(service=service)
    results = use_case.run_batch(["Tesla news.", "Apple news.", ""])
    assert len(results) == 3
    assert results[0].skipped is False
    assert results[1].skipped is False
    assert results[2].skipped is True


# ---------------------------------------------------------------------------
# 5. Cluster assignment
# ---------------------------------------------------------------------------

def test_assign_to_story_joins_nearest_above_threshold() -> None:
    assigner = AssignToStory(threshold=0.75)
    vec = _unit_vec(4, 0)
    # Story 1: same direction (similarity ~1.0)
    active = [("story-1", _unit_vec(4, 0), 3), ("story-2", _unit_vec(4, 1), 2)]
    result = assigner.assign("art-1", vec, active)
    assert result.created is False
    assert result.story_id == "story-1"
    assert result.similarity > 0.9


def test_assign_to_story_creates_new_when_no_close_story() -> None:
    assigner = AssignToStory(threshold=0.75)
    vec = _unit_vec(4, 0)
    # All stories are orthogonal → similarity = 0
    active = [("story-1", _unit_vec(4, 1), 5), ("story-2", _unit_vec(4, 2), 3)]
    result = assigner.assign("art-1", vec, active)
    assert result.created is True
    assert result.story_id == ""


def test_assign_to_story_empty_active_list_creates_new() -> None:
    assigner = AssignToStory(threshold=0.75)
    vec = [0.5, 0.5, 0.5, 0.5]
    result = assigner.assign("art-1", vec, [])
    assert result.created is True


def test_update_centroid_single_article() -> None:
    old = [1.0, 0.0, 0.0, 0.0]
    new_vec = [0.0, 1.0, 0.0, 0.0]
    centroid = update_centroid(old, 1, new_vec)
    # Running average of [1,0,0,0] and [0,1,0,0] = [0.5,0.5,0,0] normalised
    norm = math.sqrt(0.5**2 + 0.5**2)
    assert centroid[0] == pytest.approx(0.5 / norm, abs=1e-6)
    assert centroid[1] == pytest.approx(0.5 / norm, abs=1e-6)


# ---------------------------------------------------------------------------
# 6. Feed cache round-trip
# ---------------------------------------------------------------------------

def test_feed_cache_serialise_deserialise_round_trip() -> None:
    from app.application.use_cases.search.feed_types import InsightItem, RecommendationItem

    story = StoryPayload(
        id="s1",
        title="Tesla Q2 Earnings Beat Expectations",
        status="active",
        risk_level="medium",
        primary_entity_id="eid-1",
        entity_name="Tesla, Inc.",
        article_count=5,
        articles=[
            ArticleSummaryItem(
                id="a1", headline="Tesla beats Q2 earnings",
                publisher="Reuters", published_at="2026-07-01T00:00:00",
                sentiment_label="positive",
            )
        ],
        insight=InsightItem(
            what_happened="Tesla reported Q2 EPS above consensus.",
            why_happened="Strong EV demand and cost reduction.",
            model_used="claude-haiku",
        ),
        cluster_member_ids=["a1", "a2", "a3"],
        recommendations=[
            RecommendationItem(
                id="r1", audience="exec",
                recommendation_text="Prepare investor comms.",
                risk_level="low", confidence_score=0.92, needs_human_review=False,
            )
        ],
        updated_at="2026-07-16T10:00:00",
    )

    raw = serialise_payloads([story])
    restored = _deserialise_payloads(raw)

    assert len(restored) == 1
    r = restored[0]
    assert r.id == "s1"
    assert r.title == "Tesla Q2 Earnings Beat Expectations"
    assert r.risk_level == "medium"
    assert r.insight is not None
    assert r.insight.what_happened == "Tesla reported Q2 EPS above consensus."
    assert r.insight.model_used == "claude-haiku"
    assert len(r.cluster_member_ids) == 3
    assert len(r.recommendations) == 1
    assert r.recommendations[0].confidence_score == pytest.approx(0.92)
    assert len(r.articles) == 1
    assert r.articles[0].publisher == "Reuters"


def test_feed_cache_multiple_stories_ordered() -> None:
    stories = [
        StoryPayload(
            id=f"s{i}", title=f"Story {i}", status="active", risk_level="low",
            primary_entity_id="eid-1", entity_name="Tesla",
            article_count=i + 1, updated_at="2026-07-16T00:00:00",
        )
        for i in range(5)
    ]
    raw = serialise_payloads(stories)
    restored = _deserialise_payloads(raw)
    assert [r.id for r in restored] == [f"s{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# 7. GetFeed — full Fast Path (warm alias + warm feed cache)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_fast_path_zero_db_calls() -> None:
    """Fast Path with warm alias + warm feed cache: 0 DB calls, 2 Redis GETs."""
    stories = [
        StoryPayload(
            id=f"s{i}", title=f"Story {i}", status="active", risk_level="low",
            primary_entity_id="eid-1", entity_name="Tesla",
            article_count=2, updated_at="2026-07-16T00:00:00",
        )
        for i in range(3)
    ]
    cache = _FakeCache({
        "vt:alias:tesla": b"eid-1\x00Tesla, Inc.",
        feed_cache_key("eid-1"): serialise_payloads(stories),
    })
    db_calls = []

    async def _tracking_db(sql: str, params: dict[str, Any]) -> list[dict]:
        db_calls.append(sql)
        return []

    use_case = GetFeed(cache=cache, dispatcher=_FakeDispatcher(), db_query=_tracking_db)
    page = await use_case.execute("Tesla")

    assert page.path == "fast"
    assert len(page.stories) == 3
    assert len(db_calls) == 0  # zero DB calls — alias and feed both from cache


@pytest.mark.asyncio
async def test_full_cold_path_populates_alias_cache() -> None:
    """Cold Path for unknown keyword populates alias cache and dispatches tracking."""
    cache = _FakeCache()
    dispatcher = _FakeDispatcher()
    db = _make_db_stub(entity_rows=[], story_rows=[])

    use_case = GetFeed(cache=cache, dispatcher=dispatcher, db_query=db)
    page = await use_case.execute("brand-new-keyword")

    assert page.path == "cold"
    # Alias cache should be populated
    assert cache._data.get("vt:alias:brand-new-keyword") is not None
    # Background tracking should be dispatched
    assert any(c["task"] == "tasks.search.track_new_entity.run" for c in dispatcher.calls)


# ---------------------------------------------------------------------------
# 8. End-to-end sequential pipeline (in-memory)
# ---------------------------------------------------------------------------

def test_end_to_end_pipeline_normalize_dedup_embed_cluster() -> None:
    """Exercise all pure pipeline stages in sequence without any I/O."""
    # Stage 1: normalize
    raw_html = "<p>Tesla's Q2 earnings beat Wall Street expectations by 15 cents per share.</p>"
    clean_content, lang = normalize_article(raw_html)
    assert "Tesla" in clean_content
    assert "<" not in clean_content
    assert lang in {"en", "unknown"}

    # Stage 2: dedup check — not a duplicate (fresh LSH index)
    lsh = build_lsh_index()
    mh = compute_minhash(clean_content)
    assert find_duplicate(lsh, mh) is None
    add_to_index(lsh, "article-001", mh)

    # Stage 3: embed
    svc = _FakeEmbeddingService()
    embed_uc = EmbedArticle(service=svc)
    result = embed_uc.run(clean_content)
    assert result.skipped is False
    assert len(result.vector) == 4

    # Stage 4: cluster assignment (no active stories → new story created)
    assigner = AssignToStory(threshold=0.75)
    assignment = assigner.assign("article-001", result.vector, [])
    assert assignment.created is True

    # Stage 5: serialize payload into cache
    payload = StoryPayload(
        id="story-001",
        title="Tesla Q2 Earnings Beat Expectations",
        status="active",
        risk_level="low",
        primary_entity_id="eid-1",
        entity_name="Tesla",
        article_count=1,
        articles=[
            ArticleSummaryItem(
                id="article-001",
                headline="Tesla Q2 beats",
                publisher="Reuters",
                published_at="2026-07-16T00:00:00",
                sentiment_label="positive",
            )
        ],
        updated_at="2026-07-16T00:00:00",
    )
    raw_cache = serialise_payloads([payload])
    restored = _deserialise_payloads(raw_cache)
    assert len(restored) == 1
    assert restored[0].id == "story-001"
    assert len(restored[0].articles) == 1


@pytest.mark.asyncio
async def test_end_to_end_pipeline_second_article_joins_story() -> None:
    """Second article with similar embedding joins the first story."""
    svc = _FakeEmbeddingService()
    embed_uc = EmbedArticle(service=svc)
    assigner = AssignToStory(threshold=0.6)  # lower threshold for test determinism

    # First article: embed
    content_1 = "Tesla earnings beat expectations for the second quarter."
    r1 = embed_uc.run(content_1)
    # First: creates new story
    result1 = assigner.assign("art-1", r1.vector, [])
    assert result1.created is True

    # Compute centroid after first article (it's the article's vector)
    centroid = r1.vector
    active_stories = [("story-001", centroid, 1)]

    # Second article: very similar content → same vector
    r2 = embed_uc.run(content_1)  # identical content → identical embedding
    result2 = assigner.assign("art-2", r2.vector, active_stories)
    assert result2.created is False
    assert result2.story_id == "story-001"
    assert result2.similarity > 0.99  # identical vectors → similarity ≈ 1.0
