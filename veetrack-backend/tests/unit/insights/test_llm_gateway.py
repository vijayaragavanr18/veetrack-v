"""Unit tests: RoutingLLMGateway — routing, circuit breaker, retry."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.domain.exceptions import ServiceUnavailableError
from app.infrastructure.llm.llm_gateway import RoutingLLMGateway


def _make_gateway(
    local_result: Any = "local-response",
    hosted_result: Any = "hosted-response",
    local_error: Exception | None = None,
    hosted_error: Exception | None = None,
) -> RoutingLLMGateway:
    local = AsyncMock()
    local.model_name = "qwen3-4b"
    if local_error:
        local.complete = AsyncMock(side_effect=local_error)
        local.complete_json = AsyncMock(side_effect=local_error)
    else:
        local.complete = AsyncMock(return_value=local_result)
        local.complete_json = AsyncMock(return_value=local_result)

    hosted = AsyncMock()
    hosted.model_name = "claude-haiku"
    if hosted_error:
        hosted.complete = AsyncMock(side_effect=hosted_error)
        hosted.complete_json = AsyncMock(side_effect=hosted_error)
    else:
        hosted.complete = AsyncMock(return_value=hosted_result)
        hosted.complete_json = AsyncMock(return_value=hosted_result)

    return RoutingLLMGateway(
        local_client=local,
        hosted_client=hosted,
        redis=None,  # disable circuit breaker for unit tests
        default_tier="hosted",
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_to_hosted_by_default() -> None:
    gw = _make_gateway()
    result = await gw.complete("hello")
    assert result == "hosted-response"


@pytest.mark.asyncio
async def test_routes_to_local_when_specified() -> None:
    gw = _make_gateway()
    result = await gw.complete("hello", model_tier="local")
    assert result == "local-response"


@pytest.mark.asyncio
async def test_complete_json_routes_correctly() -> None:
    gw = _make_gateway(hosted_result={"what_happened": "x", "why_happened": "y"})
    result = await gw.complete_json("prompt", {})
    assert result == {"what_happened": "x", "why_happened": "y"}


@pytest.mark.asyncio
async def test_model_name_reflects_default_tier() -> None:
    gw = _make_gateway()
    assert gw.model_name == "claude-haiku"


# ---------------------------------------------------------------------------
# Retry on transient error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_on_transient_error() -> None:
    hosted = AsyncMock()
    hosted.model_name = "claude"
    # Fail twice, succeed on third attempt
    hosted.complete = AsyncMock(
        side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), "ok"]
    )
    local = AsyncMock()
    local.model_name = "qwen"
    local.complete = AsyncMock(return_value="local-ok")

    gw = RoutingLLMGateway(local, hosted, redis=None, default_tier="hosted")
    result = await gw.complete("hello")
    assert result == "ok"
    assert hosted.complete.call_count == 3


@pytest.mark.asyncio
async def test_raises_after_max_retries() -> None:
    gw = _make_gateway(hosted_error=RuntimeError("persistent failure"))
    with pytest.raises(ServiceUnavailableError, match="3 attempts"):
        await gw.complete("hello")


# ---------------------------------------------------------------------------
# Circuit breaker does not re-raise ServiceUnavailableError on retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_unavailable_not_retried() -> None:
    hosted = AsyncMock()
    hosted.model_name = "claude"
    hosted.complete = AsyncMock(side_effect=ServiceUnavailableError("circuit open"))
    local = AsyncMock()
    local.model_name = "qwen"
    local.complete = AsyncMock(return_value="ok")

    gw = RoutingLLMGateway(local, hosted, redis=None, default_tier="hosted")
    with pytest.raises(ServiceUnavailableError):
        await gw.complete("hello")
    # Should not retry — only one call
    assert hosted.complete.call_count == 1
