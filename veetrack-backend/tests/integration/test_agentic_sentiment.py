"""Integration tests for agentic sentiment adjudication (Phase 13 revised).

Runs against:
  - Local PostgreSQL DB (via docker-compose)
  - Local Ollama running qwen2.5:7b

Checks that the agent correctly adjudicates low-confidence and sarcastic sentiment.
"""

from __future__ import annotations

import os
import uuid
import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.entities import Article, Entity
from app.domain.interfaces.services import SentimentResult
from app.infrastructure.db.models.source import SourceModel
from app.infrastructure.db.repositories.article import SqlAlchemyArticleRepository
from app.infrastructure.db.repositories.entity import SqlAlchemyEntityRepository
from app.application.use_cases.sentiment.analyze_sentiment import AnalyzeSentiment
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.llm_gateway import RoutingLLMGateway
from app.infrastructure.llm.tools.get_classifier_breakdown import get_classifier_breakdown
from app.infrastructure.llm.tools.get_entity_sentiment_baseline import get_entity_sentiment_baseline


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
async def test_agentic_sentiment_sarcastic_article(db_session: AsyncSession) -> None:
    """A sarcastic article with a positive headline but negative body should be adjudicated as negative."""
    article_repo = SqlAlchemyArticleRepository(db_session)
    entity_repo = SqlAlchemyEntityRepository(db_session)

    # 1. Seed entity and baseline sentiment history
    entity = Entity(
        id=str(uuid.uuid4()),
        canonical_name="ScandalCorp",
        type="company",
    )
    await entity_repo.save(entity)

    # 2. Insert source and article with sarcastic context
    source = SourceModel(id=str(uuid.uuid4()), type="newsdata")
    db_session.add(source)
    await db_session.flush()

    headline = "ScandalCorp wins 'Worst Employer' award in a stunning victory"
    clean_content = "Employees at ScandalCorp are celebrating a new milestone today as the company was officially recognized for having the most toxic workplace environment in the sector. Despite the upbeat PR spin, insiders report plummeting morale and massive layoffs."
    
    art = await article_repo.save(
        Article(
            source_id=source.id,
            external_id=str(uuid.uuid4()),
            url="https://example.com/scandal",
            headline=headline,
            clean_content=clean_content,
            publisher="SatireDaily",
            dedup_hash=str(uuid.uuid4()),
            sentiment_label="positive",  # The naive classifier was confused by "wins", "victory", "celebrating"
            sentiment_score=0.45,
        )
    )
    
    # Manually insert entity association to let the tool find it
    from sqlalchemy import text
    await db_session.execute(
        text("INSERT INTO article_entities (article_id, entity_id) VALUES (:aid, :eid)"),
        {"aid": art.id, "eid": entity.id}
    )
    
    # 3. Setup LLM Gateway and tools bound to DB query
    async def db_query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        result = await db_session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]

    async def call_get_classifier_breakdown(args: dict[str, Any]) -> str:
        return await get_classifier_breakdown(args, db_query)

    async def call_get_entity_sentiment_baseline(args: dict[str, Any]) -> str:
        return await get_entity_sentiment_baseline(args, db_query)

    tools = {
        "get_classifier_breakdown": call_get_classifier_breakdown,
        "get_entity_sentiment_baseline": call_get_entity_sentiment_baseline,
    }

    local_client = OllamaClient(model="qwen2.5:7b", endpoint="http://localhost:11434/v1/chat/completions")
    gateway = RoutingLLMGateway(local_client=local_client, default_tier="local")

    class DummySentimentService:
        pass

    uc = AnalyzeSentiment(service=DummySentimentService())  # type: ignore

    # Simulate classifier output (low confidence or conflicting)
    headline_res = SentimentResult(label="positive", score=0.85)
    body_res = SentimentResult(label="negative", score=0.55)

    from unittest.mock import patch
    from app.application.use_cases.shared.agent_loop import AgentLoop

    original_run = AgentLoop.run
    loop_results = []

    async def wrapped_run(self, *args, **kwargs):
        res = await original_run(self, *args, **kwargs)
        loop_results.append(res)
        return res

    with patch("app.application.use_cases.shared.agent_loop.AgentLoop.run", wrapped_run):
        try:
            resolved = await uc.adjudicate(
                article_id=art.id,
                headline_result=headline_res,
                body_result=body_res,
                gateway=gateway,
                tools=tools,
            )
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

    # The agent should recognize the sarcasm ("Worst Employer", "toxic workplace") and label it negative
    assert resolved.label == "negative"
    assert resolved.low_confidence is False
