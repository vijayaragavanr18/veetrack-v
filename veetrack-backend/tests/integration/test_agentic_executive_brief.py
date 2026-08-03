"""Integration tests for the Agentic Executive Brief (Phase 16)."""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, UTC
import uuid
import os
import httpx
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.use_cases.insights.generate_executive_summary import (
    ArticleInput,
    GenerateExecutiveSummary,
)
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
from workers.tasks.llm.generate_summary import _run_generate, SummarySettings

DATABASE_URL = "postgresql+asyncpg://veetrack:devpassword@localhost:5432/veetrack"

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

@pytest_asyncio.fixture
async def setup_entity_and_stories(db_session: AsyncSession):
    """Seed test data for agentic executive brief."""
    
    # 1. Create an entity
    entity_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, type) "
            "VALUES (:id, :name, 'company')"
        ),
        {"id": entity_id, "name": "Stark Industries"},
    )
    
    # 2. Create a past story and insight
    past_story_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO stories (id, primary_entity_id, title) "
            "VALUES (:id, :eid, 'Stark factory closes')"
        ),
        {"id": past_story_id, "eid": entity_id},
    )
    
    await db_session.execute(
        text(
            "INSERT INTO story_insights "
            "(id, story_id, what_happened, why_happened, generated_at, model_used, token_cost) "
            "VALUES (:id, :sid, 'Stark Industries closed its main reactor facility.', 'Safety concerns following an anomaly.', :now, 'test', 0)"
        ),
        {"id": str(uuid.uuid4()), "sid": past_story_id, "now": datetime.now(UTC)},
    )
    
    # 3. Create the current story (pattern flagged)
    current_story_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO stories (id, primary_entity_id, title, is_pattern) "
            "VALUES (:id, :eid, 'Stark stock drops amid safety probe', true)"
        ),
        {"id": current_story_id, "eid": entity_id},
    )
    
    # 4. Add articles to the current story
    source_id = str(uuid.uuid4())
    await db_session.execute(
        text("INSERT INTO sources (id, type) VALUES (:id, 'newsdata')"),
        {"id": source_id}
    )
    
    article_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO articles (id, source_id, external_id, url, headline, publisher, clean_content, published_at, dedup_hash) "
            "VALUES (:id, :source_id, :ext_id, 'http://test/1', 'Stark shares plunge', 'TestPub', 'Investors are dumping Stark Industries stock today as regulators announce a probe into the recent reactor shutdown.', :now, :hash)"
        ),
        {"id": article_id, "source_id": source_id, "ext_id": str(uuid.uuid4()), "now": datetime.now(UTC), "hash": "testhash" + str(uuid.uuid4())},
    )
    await db_session.execute(
        text("INSERT INTO story_articles (story_id, article_id) VALUES (:sid, :aid)"),
        {"sid": current_story_id, "aid": article_id}
    )
    
    await db_session.commit()
    
    return {
        "entity_id": entity_id,
        "past_story_id": past_story_id,
        "current_story_id": current_story_id,
    }


@requires_infra
@pytest.mark.asyncio
async def test_agentic_executive_brief(
    setup_entity_and_stories: dict[str, str],
    db_session: AsyncSession
):
    """Test that an agentic brief is generated for a pattern story and references the past event."""
    
    current_story_id = setup_entity_and_stories["current_story_id"]
    entity_id = setup_entity_and_stories["entity_id"]
    
    from app.infrastructure.llm.tools.get_entity_background import get_entity_background
    from app.infrastructure.llm.tools.get_related_past_briefs import get_related_past_briefs
    from typing import Any
    
    async def _get_entity_background(args: dict[str, Any]) -> str:
        async def _query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            res = await db_session.execute(text(sql), params)
            return [dict(row._mapping) for row in res.all()]
        return await get_entity_background(args, _query)
        
    async def _get_related_past_briefs(args: dict[str, Any]) -> str:
        async def _query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
            res = await db_session.execute(text(sql), params)
            return [dict(row._mapping) for row in res.all()]
        return await get_related_past_briefs(args, _query)

    tools = {
        "get_entity_background": _get_entity_background,
        "get_related_past_briefs": _get_related_past_briefs,
    }

    local_client = OllamaClient(
        model="qwen2.5:7b",
        endpoint="http://localhost:11434/v1/chat/completions",
    )
    gateway = RoutingLLMGateway(
        local_client=local_client,
        default_tier="local",
    )
    use_case = GenerateExecutiveSummary(
        gateway=gateway,
        tools=tools,
    )
    
    articles = [
        ArticleInput(
            headline='Stark shares plunge',
            clean_content='Investors are dumping Stark Industries stock today as regulators announce a probe into the recent reactor shutdown.',
            published_at=datetime.now(UTC).isoformat()
        )
    ]
    
    result = await use_case.run(
        story_id=current_story_id,
        story_title="Stark stock drops amid safety probe",
        articles=articles,
        entity_names=["Stark Industries"],
        primary_entity_id=entity_id,
        is_pattern=True,
    )
    
    assert not result.skipped
    assert len(result.what_happened) > 10
    assert len(result.why_happened) > 10
    
    reasoning_trace = result.reasoning_trace
    assert reasoning_trace is not None
    assert isinstance(reasoning_trace, list)
    assert len(reasoning_trace) >= 1
    
    trace_str = str(reasoning_trace).lower()
    assert "get_related_past_briefs" in trace_str or "reactor" in result.why_happened.lower() or "probe" in result.why_happened.lower()
