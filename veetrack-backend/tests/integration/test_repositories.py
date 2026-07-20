"""Integration tests for SQLAlchemy repository implementations.

Requires Docker Compose to be running:
  docker compose -f infra/docker-compose.yml --env-file .env up -d

Each test uses a fresh transaction that is rolled back after the test,
so tests are fully isolated without truncating tables.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Skip marker
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://veetrack:devpassword@localhost:5432/veetrack",
)


def _db_reachable() -> bool:
    import asyncio

    async def _check() -> bool:
        try:
            engine = create_async_engine(DATABASE_URL, echo=False)
            async with engine.connect():
                pass
            await engine.dispose()
            return True
        except Exception:
            return False

    return asyncio.run(_check())


requires_db = pytest.mark.skipif(
    not _db_reachable(),
    reason="Postgres not reachable — start Docker Compose before running integration tests",
)

# ---------------------------------------------------------------------------
# Session fixture — each test gets a rolled-back transaction
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session, session.begin():
        yield session
        await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers to build minimal prerequisite rows
# ---------------------------------------------------------------------------

from app.domain.entities import (  # noqa: E402
    Article,
    Entity,
    Story,
    StoryInsight,
    StoryRecommendation,
    User,
    Workspace,
)
from app.infrastructure.db.models.source import SourceModel  # noqa: E402
from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository  # noqa: E402
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository  # noqa: E402
from app.infrastructure.db.repositories.story import SqlAlchemyStoryRepository  # noqa: E402
from app.infrastructure.db.repositories.story_insight import (  # noqa: E402
    SqlAlchemyStoryInsightRepository,
)
from app.infrastructure.db.repositories.story_recommendation import (  # noqa: E402
    SqlAlchemyStoryRecommendationRepository,
)
from app.infrastructure.db.repositories.user import SqlAlchemyUserRepository  # noqa: E402
from app.infrastructure.db.repositories.workspace import SqlAlchemyWorkspaceRepository  # noqa: E402


async def _make_source(session: AsyncSession) -> str:
    """Insert a minimal source row and return its id."""
    import uuid

    source = SourceModel(id=str(uuid.uuid4()), type="newsdata")
    session.add(source)
    await session.flush()
    return source.id


async def _make_workspace(session: AsyncSession) -> Workspace:
    repo = SqlAlchemyWorkspaceRepository(session)
    return await repo.save(Workspace(name="Acme Corp", plan="pro"))


async def _make_entity(session: AsyncSession) -> Entity:
    repo = SqlAlchemyEntityRepository(session)
    return await repo.save(Entity(canonical_name="Tesla, Inc.", type="company"))


async def _make_story(session: AsyncSession, entity_id: str) -> Story:
    repo = SqlAlchemyStoryRepository(session)
    return await repo.save(Story(primary_entity_id=entity_id, title="Tesla Q2 Earnings"))


async def _make_article(session: AsyncSession, source_id: str) -> Article:
    repo = SqlAlchemyArticleRepository(session)
    return await repo.save(
        Article(
            source_id=source_id,
            external_id="ext-001",
            url="https://example.com/article/1",
            headline="Tesla beats estimates",
            publisher="Reuters",
            dedup_hash="abc123unique",
        )
    )


# ---------------------------------------------------------------------------
# Workspace tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_workspace_save_and_get(db_session: AsyncSession) -> None:
    repo = SqlAlchemyWorkspaceRepository(db_session)
    ws = await repo.save(Workspace(name="Test Corp", plan="free"))
    fetched = await repo.get_by_id(ws.id)
    assert fetched.id == ws.id
    assert fetched.name == "Test Corp"
    assert fetched.plan == "free"


@requires_db
@pytest.mark.asyncio
async def test_workspace_update(db_session: AsyncSession) -> None:
    repo = SqlAlchemyWorkspaceRepository(db_session)
    ws = await repo.save(Workspace(name="Old Name", plan="free"))
    ws.name = "New Name"
    ws.plan = "pro"
    updated = await repo.save(ws)
    assert updated.name == "New Name"
    assert updated.plan == "pro"


@requires_db
@pytest.mark.asyncio
async def test_workspace_not_found(db_session: AsyncSession) -> None:
    from app.domain.exceptions import NotFoundError

    repo = SqlAlchemyWorkspaceRepository(db_session)
    with pytest.raises(NotFoundError):
        await repo.get_by_id("nonexistent-id")


# ---------------------------------------------------------------------------
# User tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_user_save_and_get(db_session: AsyncSession) -> None:
    ws = await _make_workspace(db_session)
    repo = SqlAlchemyUserRepository(db_session)
    user = await repo.save(
        User(
            workspace_id=ws.id, email="alice@example.com", role="analyst", hashed_password="hashed"
        )
    )
    fetched = await repo.get_by_id(user.id)
    assert fetched.email == "alice@example.com"
    assert fetched.role == "analyst"


@requires_db
@pytest.mark.asyncio
async def test_user_get_by_email(db_session: AsyncSession) -> None:
    ws = await _make_workspace(db_session)
    repo = SqlAlchemyUserRepository(db_session)
    await repo.save(
        User(workspace_id=ws.id, email="bob@example.com", role="viewer", hashed_password="hashed")
    )
    found = await repo.get_by_email("bob@example.com", ws.id)
    assert found is not None
    assert found.email == "bob@example.com"

    not_found = await repo.get_by_email("nobody@example.com", ws.id)
    assert not_found is None


# ---------------------------------------------------------------------------
# Entity tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_entity_save_and_get(db_session: AsyncSession) -> None:
    repo = SqlAlchemyEntityRepository(db_session)
    entity = await repo.save(
        Entity(canonical_name="Apple Inc.", type="company", metadata={"sector": "tech"})
    )
    fetched = await repo.get_by_id(entity.id)
    assert fetched.canonical_name == "Apple Inc."
    assert fetched.metadata["sector"] == "tech"


@requires_db
@pytest.mark.asyncio
async def test_entity_resolve_alias(db_session: AsyncSession) -> None:
    from app.infrastructure.db.models.entity_alias import EntityAliasModel

    repo = SqlAlchemyEntityRepository(db_session)
    entity = await repo.save(Entity(canonical_name="Tesla, Inc.", type="company"))

    alias = EntityAliasModel(entity_id=entity.id, alias_text="$TSLA", alias_type="ticker")
    db_session.add(alias)
    await db_session.flush()

    resolved = await repo.resolve_alias("$TSLA")
    assert resolved is not None
    assert resolved.id == entity.id

    no_match = await repo.resolve_alias("$UNKNOWN")
    assert no_match is None


# ---------------------------------------------------------------------------
# Article tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_article_save_and_get(db_session: AsyncSession) -> None:
    source_id = await _make_source(db_session)
    repo = SqlAlchemyArticleRepository(db_session)
    article = await repo.save(
        Article(
            source_id=source_id,
            external_id="ext-001",
            url="https://news.example.com/1",
            headline="Breaking: market rally",
            publisher="Bloomberg",
            dedup_hash="hash-001",
        )
    )
    fetched = await repo.get_by_id(article.id)
    assert fetched.headline == "Breaking: market rally"
    assert fetched.dedup_hash == "hash-001"


@requires_db
@pytest.mark.asyncio
async def test_article_find_by_dedup_hash(db_session: AsyncSession) -> None:
    source_id = await _make_source(db_session)
    repo = SqlAlchemyArticleRepository(db_session)
    await repo.save(
        Article(
            source_id=source_id,
            external_id="e1",
            url="https://a.com",
            headline="H",
            publisher="P",
            dedup_hash="unique-hash-xyz",
        )
    )
    found = await repo.find_by_dedup_hash("unique-hash-xyz")
    assert found is not None
    assert found.dedup_hash == "unique-hash-xyz"

    miss = await repo.find_by_dedup_hash("does-not-exist")
    assert miss is None


@requires_db
@pytest.mark.asyncio
async def test_article_duplicate_dedup_hash_raises_conflict(db_session: AsyncSession) -> None:
    from app.domain.exceptions import ConflictError

    source_id = await _make_source(db_session)
    repo = SqlAlchemyArticleRepository(db_session)
    await repo.save(
        Article(
            source_id=source_id,
            external_id="e1",
            url="https://a.com",
            headline="H",
            publisher="P",
            dedup_hash="dup-hash",
        )
    )
    with pytest.raises(ConflictError):
        await repo.save(
            Article(
                source_id=source_id,
                external_id="e2",
                url="https://b.com",
                headline="H2",
                publisher="P",
                dedup_hash="dup-hash",
            )
        )


# ---------------------------------------------------------------------------
# Story tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_story_save_and_get(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    repo = SqlAlchemyStoryRepository(db_session)
    story = await repo.save(
        Story(primary_entity_id=entity.id, title="Tesla IPO news", status="active")
    )
    fetched = await repo.get_by_id(story.id)
    assert fetched.title == "Tesla IPO news"
    assert fetched.status == "active"


@requires_db
@pytest.mark.asyncio
async def test_story_list_by_entity(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    repo = SqlAlchemyStoryRepository(db_session)
    await repo.save(Story(primary_entity_id=entity.id, title="Story A"))
    await repo.save(Story(primary_entity_id=entity.id, title="Story B"))
    stories = await repo.list_by_entity(entity.id)
    assert len(stories) == 2


@requires_db
@pytest.mark.asyncio
async def test_story_list_by_entity_limit(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    repo = SqlAlchemyStoryRepository(db_session)
    for i in range(5):
        await repo.save(Story(primary_entity_id=entity.id, title=f"Story {i}"))
    stories = await repo.list_by_entity(entity.id, limit=3)
    assert len(stories) == 3


# ---------------------------------------------------------------------------
# Article list_by_story test
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_article_list_by_story(db_session: AsyncSession) -> None:
    from app.infrastructure.db.models.story_article import StoryArticleModel

    source_id = await _make_source(db_session)
    entity = await _make_entity(db_session)
    story = await _make_story(db_session, entity.id)

    article_repo = SqlAlchemyArticleRepository(db_session)
    a1 = await article_repo.save(
        Article(
            source_id=source_id,
            external_id="e1",
            url="https://a.com/1",
            headline="H1",
            publisher="P",
            dedup_hash="h1",
        )
    )
    a2 = await article_repo.save(
        Article(
            source_id=source_id,
            external_id="e2",
            url="https://a.com/2",
            headline="H2",
            publisher="P",
            dedup_hash="h2",
        )
    )
    db_session.add(StoryArticleModel(story_id=story.id, article_id=a1.id))
    db_session.add(StoryArticleModel(story_id=story.id, article_id=a2.id))
    await db_session.flush()

    articles = await article_repo.list_by_story(story.id)
    assert len(articles) == 2


# ---------------------------------------------------------------------------
# StoryInsight tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_story_insight_save_and_get(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    story = await _make_story(db_session, entity.id)
    repo = SqlAlchemyStoryInsightRepository(db_session)

    insight = await repo.save(
        StoryInsight(
            story_id=story.id,
            what_happened="Tesla beat Q2 estimates.",
            why_happened="Strong EV demand.",
            model_used="claude-haiku",
            token_cost=512,
        )
    )
    fetched = await repo.get_by_story_id(story.id)
    assert fetched is not None
    assert fetched.id == insight.id
    assert fetched.what_happened == "Tesla beat Q2 estimates."


@requires_db
@pytest.mark.asyncio
async def test_story_insight_returns_none_when_absent(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    story = await _make_story(db_session, entity.id)
    repo = SqlAlchemyStoryInsightRepository(db_session)
    result = await repo.get_by_story_id(story.id)
    assert result is None


# ---------------------------------------------------------------------------
# StoryRecommendation tests
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_story_recommendation_save_and_list(db_session: AsyncSession) -> None:
    entity = await _make_entity(db_session)
    story = await _make_story(db_session, entity.id)
    repo = SqlAlchemyStoryRecommendationRepository(db_session)

    await repo.save(
        StoryRecommendation(
            story_id=story.id,
            recommendation_text="Issue a statement",
            confidence_score=0.9,
            audience="pr",
        )
    )
    await repo.save(
        StoryRecommendation(
            story_id=story.id,
            recommendation_text="Brief the board",
            confidence_score=0.7,
            audience="exec",
        )
    )

    recs = await repo.list_by_story_id(story.id)
    assert len(recs) == 2
    # Should be confidence-descending
    assert recs[0].confidence_score >= recs[1].confidence_score


# ---------------------------------------------------------------------------
# Vector similarity test
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio
async def test_vector_similarity_ordering(db_session: AsyncSession) -> None:
    """Insert 3 stories with known centroids; assert nearest-neighbor ordering."""
    from sqlalchemy import text

    entity = await _make_entity(db_session)
    story_repo = SqlAlchemyStoryRepository(db_session)

    s1 = await story_repo.save(Story(primary_entity_id=entity.id, title="Near"))
    s2 = await story_repo.save(Story(primary_entity_id=entity.id, title="Mid"))
    s3 = await story_repo.save(Story(primary_entity_id=entity.id, title="Far"))

    dim = 1024
    # query vector: all 1.0 (unit direction)
    # near: all 1.0 → cosine distance = 0 (identical direction)
    # mid: first half 1.0, second half 0.0 → partial match
    # far: all -1.0 → cosine distance = 2 (opposite)
    near_vec = [1.0] * dim
    mid_vec = [1.0] * (dim // 2) + [0.0] * (dim // 2)
    far_vec = [-1.0] * dim

    await db_session.execute(
        text("UPDATE stories SET cluster_centroid = :v WHERE id = :id"),
        {"v": str(near_vec), "id": s1.id},
    )
    await db_session.execute(
        text("UPDATE stories SET cluster_centroid = :v WHERE id = :id"),
        {"v": str(mid_vec), "id": s2.id},
    )
    await db_session.execute(
        text("UPDATE stories SET cluster_centroid = :v WHERE id = :id"),
        {"v": str(far_vec), "id": s3.id},
    )
    await db_session.flush()

    query_vec = str([1.0] * dim)
    result = await db_session.execute(
        text(
            "SELECT id, cluster_centroid <=> :q AS dist "
            "FROM stories WHERE id = ANY(:ids) "
            "ORDER BY dist ASC"
        ),
        {"q": query_vec, "ids": [s1.id, s2.id, s3.id]},
    )
    rows = result.fetchall()
    ordered_ids = [r[0] for r in rows]
    assert ordered_ids[0] == s1.id, "Nearest story should be first"
    assert ordered_ids[-1] == s3.id, "Farthest story should be last"
