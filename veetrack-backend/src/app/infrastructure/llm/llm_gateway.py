"""Routing LLM gateway with retry/back-off and Redis-backed circuit breaker.

Routes calls to either:
  - ``model_tier="local"``  → OllamaClient (Qwen2.5 3B via Ollama)
  - ``model_tier="hosted"`` → HostedClient (Claude via Anthropic SDK)

The circuit breaker follows the same pattern as infrastructure/connectors/base.py:
  closed  → normal; failures increment a counter
  open    → all calls rejected; auto-resets after CIRCUIT_RESET_SECONDS

Retry: up to MAX_RETRIES attempts with exponential backoff (1s, 2s, 4s).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any, Literal

import structlog

from app.domain.exceptions import ServiceUnavailableError
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

ModelTier = Literal["local", "hosted"]

# Circuit breaker constants (same defaults as connectors/base.py)
_FAILURE_THRESHOLD = 5
_RESET_SECONDS = 120
_MAX_RETRIES = 3

# Redis circuit breaker key prefixes
_CB_FAILURES_PREFIX = "vt:cb:llm:failures:"
_CB_OPEN_UNTIL_PREFIX = "vt:cb:llm:open_until:"


class RoutingLLMGateway:
    """Routes LLM calls to local or hosted backend with circuit breaker and retry.

    Parameters
    ----------
    local_client:
        OllamaClient (or any LLMGateway-compatible object) for the local tier.
    hosted_client:
        HostedClient (or any LLMGateway-compatible object) for the hosted tier.
    redis:
        redis.asyncio.Redis instance for circuit breaker state.  If None,
        circuit breaker is disabled (useful in tests).
    default_tier:
        Which tier to use when ``complete()`` / ``complete_json()`` are called
        without an explicit ``model_tier``.
    """

    def __init__(
        self,
        local_client: LLMGateway,
        hosted_client: LLMGateway | None = None,
        redis: Any = None,
        default_tier: ModelTier = "local",
    ) -> None:
        self._clients: dict[ModelTier, LLMGateway] = {"local": local_client}
        if hosted_client is not None:
            self._clients["hosted"] = hosted_client
        self._redis = redis
        self._default_tier = default_tier

    @property
    def model_name(self) -> str:
        return self._clients[self._default_tier].model_name

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model_tier: ModelTier | None = None,
    ) -> str:
        tier: ModelTier = model_tier or self._default_tier
        return await self._with_retry_and_cb(
            tier,
            "complete",
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        max_tokens: int = 2048,
        model_tier: ModelTier | None = None,
    ) -> dict[str, Any]:
        tier: ModelTier = model_tier or self._default_tier
        return await self._with_retry_and_cb(  # type: ignore[return-value]
            tier,
            "complete_json",
            prompt,
            schema,
            system=system,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Retry + circuit breaker
    # ------------------------------------------------------------------

    async def _with_retry_and_cb(
        self,
        tier: ModelTier,
        method: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        await self._check_circuit(tier)
        client = self._clients[tier]
        fn = getattr(client, method)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                result = await fn(*args, **kwargs)
                await self._record_success(tier)
                return result
            except ServiceUnavailableError:
                raise  # don't retry on rate limit / circuit-open
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "llm_gateway.attempt_failed",
                    tier=tier,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                await self._record_failure(tier)
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2**attempt)  # 1s, 2s, 4s

        raise ServiceUnavailableError(
            f"LLM {tier} tier failed after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    async def _check_circuit(self, tier: ModelTier) -> None:
        if self._redis is None:
            return
        key = f"{_CB_OPEN_UNTIL_PREFIX}{tier}"
        val = await self._redis.get(key)
        if val is None:
            return
        open_until = float(val)
        if time.time() < open_until:
            raise ServiceUnavailableError(
                f"LLM {tier} circuit open until "
                f"{datetime.fromtimestamp(open_until, tz=UTC).isoformat()}"
            )
        await self._redis.delete(key)

    async def _record_success(self, tier: ModelTier) -> None:
        if self._redis is None:
            return
        await self._redis.delete(f"{_CB_FAILURES_PREFIX}{tier}")

    async def _record_failure(self, tier: ModelTier) -> None:
        if self._redis is None:
            return
        failures_key = f"{_CB_FAILURES_PREFIX}{tier}"
        count = await self._redis.incr(failures_key)
        await self._redis.expire(failures_key, _RESET_SECONDS * 2)
        if count >= _FAILURE_THRESHOLD:
            open_until = time.time() + _RESET_SECONDS
            await self._redis.set(f"{_CB_OPEN_UNTIL_PREFIX}{tier}", str(open_until))
            await self._redis.delete(failures_key)
            logger.warning(
                "llm_gateway.circuit_opened",
                tier=tier,
                open_until=datetime.fromtimestamp(open_until, tz=UTC).isoformat(),
            )


# Static protocol conformance check
_: LLMGateway = RoutingLLMGateway.__new__(RoutingLLMGateway)
