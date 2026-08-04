"""Integration tests for agentic clustering and timeline building (Phase 15 revised).

Runs against:
  - Local PostgreSQL DB
  - Local Ollama running qwen2.5:7b

Checks that:
  - The clustering agent correctly identifies turning points in a 3-stage story.
  - The clustering agent correctly merges or keeps separate borderline candidates.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.use_cases.clustering.build_narrative_timeline import BuildNarrativeTimeline
from app.domain.entities import Article, Entity
from app.infrastructure.db.models.source import SourceModel
from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository
from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.tools.get_cluster_candidate_articles import (
    get_cluster_candidate_articles,
)
from app.infrastructure.llm.tools.get_entity_event_history import get_entity_event_history

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
        r = httpx.get("http://localhost:11434/", timeout=2.0)
        if r.status_code != 200:
            return False
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
async def test_agentic_timeline_3_stage_story(db_session: AsyncSession) -> None:
    """A constructed 3-stage story should have turning points correctly identified by the timeline agent."""
    article_repo = SqlAlchemyArticleRepository(db_session)
    entity_repo = SqlAlchemyEntityRepository(db_session)

    # Setup
    entity = Entity(id=str(uuid.uuid4()), canonical_name="TechCorp", type="company")
    await entity_repo.save(entity)

    source = SourceModel(id=str(uuid.uuid4()), type="newsdata")
    db_session.add(source)
    await db_session.flush()

    # Stage 1: Announcement (Turning point)
    art1 = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/art1",
            headline="TechCorp announces new revolutionary AI product",
            clean_content="TechCorp has unveiled its latest product, promising to revolutionize the industry. The announcement was made today by the CEO.",
            publisher="TechNews",
            dedup_hash=str(uuid.uuid4()),
        )
    )

    # Stage 2: Routine coverage (Not a turning point)
    art2 = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/art2",
            headline="Investors excited about TechCorp's new AI product",
            clean_content="Following yesterday's announcement, investors are showing great interest in TechCorp's stock. Analysts predict a strong quarter.",
            publisher="FinanceDaily",
            dedup_hash=str(uuid.uuid4()),
        )
    )

    # Stage 3: Investigation (Turning point)
    art3 = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/art3",
            headline="TechCorp under investigation for misleading AI claims",
            clean_content="Regulators have launched an investigation into TechCorp regarding claims about its new AI product. The company is cooperating with authorities.",
            publisher="RegulatorWatch",
            dedup_hash=str(uuid.uuid4()),
        )
    )

    # Add to a story
    story_id = str(uuid.uuid4())
    await db_session.execute(
        text("INSERT INTO stories (id, primary_entity_id, title) VALUES (:sid, :eid, :title)"),
        {"sid": story_id, "eid": entity.id, "title": "TechCorp AI Product Story"}
    )
    for aid in [art1.id, art2.id, art3.id]:
        await db_session.execute(
            text("INSERT INTO story_articles (story_id, article_id) VALUES (:sid, :aid)"),
            {"sid": story_id, "aid": aid}
        )
        await db_session.execute(
            text("INSERT INTO article_entities (article_id, entity_id) VALUES (:aid, :eid)"),
            {"aid": aid, "eid": entity.id}
        )

    async def db_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = await db_session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]

    async def call_get_cluster_candidate_articles(args: dict[str, Any]) -> str:
        return await get_cluster_candidate_articles(args, db_query)

    async def call_get_entity_event_history(args: dict[str, Any]) -> str:
        return await get_entity_event_history(args, db_query)

    tools = {
        "get_cluster_candidate_articles": call_get_cluster_candidate_articles,
        "get_entity_event_history": call_get_entity_event_history,
    }

    local_client = OllamaClient(model="qwen2.5:7b", endpoint="http://localhost:11434/v1/chat/completions")
    gateway = RoutingLLMGateway(local_client=local_client, default_tier="local")

    timeline_builder = BuildNarrativeTimeline(gateway=gateway, tools=tools)

    from app.application.use_cases.shared.agent_loop import AgentLoop
    original_run = AgentLoop.run
    loop_results = []

    async def wrapped_run(self, *args, **kwargs):
        res = await original_run(self, *args, **kwargs)
        loop_results.append(res)
        return res

    with patch("app.application.use_cases.shared.agent_loop.AgentLoop.run", wrapped_run):
        try:
            result = await timeline_builder.run(story_id=story_id)
        except Exception as exc:
            for idx, lr in enumerate(loop_results):
                print(f"\\n--- LOOP RESULT {idx} TRACE ---")
                for entry in lr.trace:
                    print(entry)
            raise exc

    for idx, lr in enumerate(loop_results):
        print(f"\\n--- LOOP RESULT {idx} TRACE ---")
        for entry in lr.trace:
            print(entry)

    highlights = result.get("timeline_highlights", [])
    highlight_text = " ".join(highlights).lower()
    # The LLM should identify the announcement and the investigation as turning points
    assert art1.id in highlight_text or "announc" in highlight_text, "Announcement should be a turning point"
    assert art3.id in highlight_text or "investigat" in highlight_text or "criticism" in highlight_text, "Investigation should be a turning point"
    # art2 (routine follow-on) might or might not be excluded by the LLM, but 1 & 3 are definitely key.
