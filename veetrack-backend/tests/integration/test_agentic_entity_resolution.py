"""Integration tests for agentic entity resolution (Phase 12 revised).

Runs against:
  - Local PostgreSQL DB (via docker-compose)
  - Local Ollama running qwen2.5:7b

Checks that the agent correctly disambiguates mentions using surrounding context.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.use_cases.entities.resolve_entity import ResolveEntity
from app.domain.entities import Article, Entity
from app.domain.interfaces.services import EntityMention
from app.infrastructure.db.models.source import SourceModel
from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository
from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.tools.get_article_context import get_article_context
from app.infrastructure.llm.tools.get_candidate_entities import get_candidate_entities

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://veetrack:devpassword@localhost:5432/veetrack",
)


def _db_reachable() -> bool:
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


def _ollama_reachable() -> bool:
    try:
        # Check if Ollama service is up
        r = httpx.get("http://localhost:11434/", timeout=2.0)
        if r.status_code != 200:
            return False
        # Check if qwen2.5:7b is pulled
        r = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return any("qwen2.5:7b" in m for m in models)
        return False
    except Exception:
        return False


requires_infra = pytest.mark.skipif(
    not (_db_reachable() and _ollama_reachable()),
    reason="Postgres or Ollama with qwen2.5:7b not available — start them before running integration tests",
)


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session, session.begin():
        yield session
        await session.rollback()
    await engine.dispose()


@requires_infra
@pytest.mark.asyncio
async def test_agentic_disambiguation_apel_company_context(db_session: AsyncSession) -> None:
    """An ambiguous mention of 'Apel' near 'CEO' and 'stock' should resolve to 'Apel Inc.'."""
    entity_repo = SqlAlchemyEntityRepository(db_session)
    article_repo = SqlAlchemyArticleRepository(db_session)

    # 1. Seed two entities with description in metadata_json
    entity_a = Entity(
        id=str(uuid.uuid4()),
        canonical_name="Apel Inc.",
        type="company",
        metadata={"description": "A tech giant that designs and sells iPhones, Macs, consumer electronics, and is led by CEO Tim Cook."}
    )
    entity_b = Entity(
        id=str(uuid.uuid4()),
        canonical_name="Apel Orchard",
        type="topic",
        metadata={"description": "A farm or field of apple trees grown commercially for fresh apel fruits, harvests, and cider."}
    )

    await entity_repo.save(entity_a)
    await entity_repo.save(entity_b)

    # Add aliases to make 'Apel' a fuzzy match to both but not an exact match to either
    await entity_repo.add_alias(entity_a.id, "Apel1")
    await entity_repo.add_alias(entity_b.id, "Apel2")

    # 2. Insert source and article with corporate context
    source = SourceModel(id=str(uuid.uuid4()), type="newsdata")
    db_session.add(source)
    await db_session.flush()

    headline = "Apel shares surge after new product launch"
    clean_content = "Today, Apel announced a new AI feature under CEO Tim Cook, driving their stock price to record highs."
    art = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/tech-news",
            headline=headline,
            clean_content=clean_content,
            publisher="Bloomberg",
            dedup_hash=str(uuid.uuid4()),
        )
    )

    # 3. Setup LLM Gateway and tools bound to DB query
    async def db_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        result = await db_session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]

    async def call_get_candidate_entities(args: dict[str, Any]) -> str:
        return await get_candidate_entities(args, db_query)

    async def call_get_article_context(args: dict[str, Any]) -> str:
        return await get_article_context(args, db_query)

    tools = {
        "get_candidate_entities": call_get_candidate_entities,
        "get_article_context": call_get_article_context,
    }

    local_client = OllamaClient(model="qwen2.5:7b", endpoint="http://localhost:11434/v1/chat/completions")
    gateway = RoutingLLMGateway(local_client=local_client, default_tier="local")

    resolver = ResolveEntity(
        entity_repo=entity_repo,
        gateway=gateway,
        tools=tools,
    )

    # 4. Resolve the ambiguous mention 'Apel'
    mention_offset = clean_content.find("Apel")
    mention = EntityMention(
        text="Apel",
        label="organization",
        score=0.9,
        start=mention_offset,
        end=mention_offset + 4
    )

    candidate_aliases = await entity_repo.list_all_aliases()
    resolved = await resolver.run(mention, candidate_aliases, article_id=art.id)

    assert resolved.id == entity_a.id
    assert resolved.canonical_name == "Apel Inc."


@requires_infra
@pytest.mark.asyncio
async def test_agentic_disambiguation_apel_orchard_context(db_session: AsyncSession) -> None:
    """An ambiguous mention of 'apel' near 'harvest' and 'orchard' should resolve to 'Apel Orchard'."""
    entity_repo = SqlAlchemyEntityRepository(db_session)
    article_repo = SqlAlchemyArticleRepository(db_session)

    # 1. Seed two entities with description in metadata_json
    entity_a = Entity(
        id=str(uuid.uuid4()),
        canonical_name="Apel Inc.",
        type="company",
        metadata={"description": "A tech giant that designs and sells iPhones, Macs, consumer electronics, and is led by CEO Tim Cook."}
    )
    entity_b = Entity(
        id=str(uuid.uuid4()),
        canonical_name="Apel Orchard",
        type="topic",
        metadata={"description": "A farm or field of apple trees grown commercially for fresh apel fruits, harvests, and cider."}
    )

    await entity_repo.save(entity_a)
    await entity_repo.save(entity_b)

    # Add aliases to make 'apel' a fuzzy match to both but not an exact match to either
    await entity_repo.add_alias(entity_a.id, "Apel1")
    await entity_repo.add_alias(entity_b.id, "Apel2")

    # 2. Insert source and article with agricultural context
    source = SourceModel(id=str(uuid.uuid4()), type="newsdata")
    db_session.add(source)
    await db_session.flush()

    headline = "Apel harvest festival kicks off this weekend"
    clean_content = "Farmers are preparing for the annual autumn apel harvest, bringing fresh cider and fruits to the orchard."
    art = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/agri-news",
            headline=headline,
            clean_content=clean_content,
            publisher="AgriWeekly",
            dedup_hash=str(uuid.uuid4()),
        )
    )

    # 3. Setup LLM Gateway and tools bound to DB query
    async def db_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        result = await db_session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]

    async def call_get_candidate_entities(args: dict[str, Any]) -> str:
        return await get_candidate_entities(args, db_query)

    async def call_get_article_context(args: dict[str, Any]) -> str:
        return await get_article_context(args, db_query)

    tools = {
        "get_candidate_entities": call_get_candidate_entities,
        "get_article_context": call_get_article_context,
    }

    local_client = OllamaClient(model="qwen2.5:7b", endpoint="http://localhost:11434/v1/chat/completions")
    gateway = RoutingLLMGateway(local_client=local_client, default_tier="local")

    resolver = ResolveEntity(
        entity_repo=entity_repo,
        gateway=gateway,
        tools=tools,
    )

    # 4. Resolve the ambiguous mention 'apel'
    mention_offset = clean_content.find("apel")
    mention = EntityMention(
        text="apel",
        label="topic",
        score=0.9,
        start=mention_offset,
        end=mention_offset + 4
    )

    candidate_aliases = await entity_repo.list_all_aliases()
    resolved = await resolver.run(mention, candidate_aliases, article_id=art.id)

    # The agent should pick the agricultural entity (Apel Orchard) based on harvest/orchard
    # context, NOT the tech company (Apel Inc.). This validates correct contextual
    # disambiguation: same fuzzy surface, different article context → different resolution.
    assert resolved.id == entity_b.id
    assert resolved.canonical_name == "Apel Orchard"
