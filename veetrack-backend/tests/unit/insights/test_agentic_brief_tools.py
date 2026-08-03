"""Unit tests for agentic executive brief tools."""

import pytest
from unittest.mock import AsyncMock

from app.infrastructure.llm.tools.get_entity_background import get_entity_background
from app.infrastructure.llm.tools.get_related_past_briefs import get_related_past_briefs


@pytest.mark.asyncio
async def test_get_entity_background():
    db_query = AsyncMock()
    
    async def side_effect(sql, params):
        eid = params.get("eid")
        if eid == "ent1":
            return [
                {
                    "canonical_name": "Entity One",
                    "type": "company",
                    "metadata_json": '{"description": "A test entity"}'
                }
            ]
        return []
    
    db_query.side_effect = side_effect
    
    # Test valid
    res = await get_entity_background({"entity_id": "ent1"}, db_query)
    assert "Entity One" in res
    assert "company" in res
    assert "A test entity" in res

    # Test missing
    res2 = await get_entity_background({"entity_id": "ent2"}, db_query)
    assert "No entity found" in res2


@pytest.mark.asyncio
async def test_get_related_past_briefs():
    db_query = AsyncMock()
    
    db_query.return_value = [
        {
            "title": "Story Title 1",
            "what_happened": "What 1",
            "why_happened": "Why 1",
            "created_at": "2026-07-20T00:00:00Z"
        },
        {
            "title": "Story Title 2",
            "what_happened": "What 2",
            "why_happened": "Why 2",
            "created_at": "2026-07-21T00:00:00Z"
        }
    ]
    
    res = await get_related_past_briefs({"entity_id": "ent1", "limit": 2}, db_query)
    
    assert "Recent briefs for entity ent1" in res
    assert "Story Title 1" in res
    assert "What 1" in res
    assert "Why 1" in res
    assert "Story Title 2" in res
