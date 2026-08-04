"""Unit tests for agentic clustering tools."""

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.llm.tools.get_cluster_candidate_articles import (
    get_cluster_candidate_articles,
)
from app.infrastructure.llm.tools.get_entity_event_history import get_entity_event_history


@pytest.mark.asyncio
async def test_get_cluster_candidate_articles():
    db_query = AsyncMock()
    
    # Return different articles for different story IDs
    async def side_effect(sql, params):
        sid = params.get("sid")
        if sid == "cluster1":
            return [
                {
                    "id": "a1",
                    "headline": "Headline A",
                    "clean_content": "Content A",
                    "published_at": "2026-07-22T00:00:00Z"
                }
            ]
        elif sid == "cluster2":
            return [
                {
                    "id": "a2",
                    "headline": "Headline B",
                    "clean_content": "Content B",
                    "published_at": "2026-07-22T01:00:00Z"
                }
            ]
        return []
    
    db_query.side_effect = side_effect
    
    args = {"cluster_id_a": "cluster1", "cluster_id_b": "cluster2"}
    res = await get_cluster_candidate_articles(args, db_query)
    
    assert "Headline A" in res
    assert "Content A" in res
    assert "Headline B" in res
    assert "Content B" in res


@pytest.mark.asyncio
async def test_get_entity_event_history():
    db_query = AsyncMock()
    
    db_query.return_value = [
        {
            "id": "s1",
            "title": "Story Title 1",
            "created_at": "2026-07-20T00:00:00Z"
        },
        {
            "id": "s2",
            "title": "Story Title 2",
            "created_at": "2026-07-21T00:00:00Z"
        }
    ]
    
    args = {"entity_id": "ent1"}
    res = await get_entity_event_history(args, db_query)
    
    assert "Past events for entity 'ent1':" in res
    assert "Story Title 1" in res
    assert "Story Title 2" in res

