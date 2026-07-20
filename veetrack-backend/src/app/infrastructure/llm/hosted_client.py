"""Hosted Claude client — wraps the Anthropic SDK and logs per-call usage to llm_usage_log.

Implements the LLMGateway Protocol defined in domain/interfaces/services.py.

Model tier: "hosted"
Token costs (micro-USD, approximate for claude-3-5-haiku):
  input:  $0.80 / 1M tokens  → 0.8 micro-USD per token  → multiply tokens * 8 / 10
  output: $4.00 / 1M tokens  → 4.0 micro-USD per token  → multiply tokens * 4
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Cost coefficients in micro-USD per token (approximate, haiku-tier)
_INPUT_COST_PER_TOKEN_MICRO = 0.0008  # $0.80/M  = 0.8e-6 per token
_OUTPUT_COST_PER_TOKEN_MICRO = 0.004  # $4.00/M  = 4.0e-6 per token


class HostedClient:
    """Anthropic-SDK-backed client with token/cost logging to llm_usage_log.

    Parameters
    ----------
    model:
        Anthropic model ID, e.g. ``"claude-haiku-4-5-20251001"``.
    api_key:
        Anthropic API key (required).
    db_url:
        If provided, each call inserts a row into ``llm_usage_log`` using a
        fresh asyncpg connection.  When omitted logging is skipped silently.
    story_id:
        If set, this story_id is associated with the log row.  Can be overridden
        per-call via the ``story_id`` parameter on :meth:`complete`.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        db_url: str = "",
        story_id: str = "",
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._db_url = db_url
        self._story_id = story_id

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.0,
        story_id: str = "",
    ) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self._api_key)
        t0 = time.monotonic()

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = await client.messages.create(**kwargs)

        latency_ms = int((time.monotonic() - t0) * 1000)
        input_tokens: int = message.usage.input_tokens
        output_tokens: int = message.usage.output_tokens

        await self._log_usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            story_id=story_id or self._story_id,
        )

        content = message.content[0]
        if content.type != "text":
            raise ValueError(f"Unexpected content type: {content.type}")
        return str(content.text)

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        max_tokens: int = 2048,
        story_id: str = "",
    ) -> dict[str, Any]:
        json_instruction = (
            f"\n\nRespond ONLY with a valid JSON object matching this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        text = await self.complete(
            prompt + json_instruction,
            system=system,
            max_tokens=max_tokens,
            temperature=0.0,
            story_id=story_id,
        )
        try:
            stripped = text.strip()
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                stripped = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return dict(json.loads(stripped))  # type: ignore[arg-type]
        except json.JSONDecodeError as exc:
            raise ValueError(f"Hosted LLM returned invalid JSON: {exc}\nRaw: {text[:200]}") from exc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _log_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        story_id: str,
    ) -> None:
        if not self._db_url:
            return
        cost_micro = int(
            input_tokens * _INPUT_COST_PER_TOKEN_MICRO
            + output_tokens * _OUTPUT_COST_PER_TOKEN_MICRO
        )
        try:
            import asyncpg

            conn = await asyncpg.connect(self._db_url)
            try:
                await conn.execute(
                    """
                    INSERT INTO llm_usage_log
                        (id, story_id, model_id, prompt_tokens,
                         completion_tokens, cost_usd_micro, latency_ms)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    str(uuid.uuid4()),
                    story_id or None,
                    self._model,
                    input_tokens,
                    output_tokens,
                    cost_micro,
                    latency_ms,
                )
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("hosted_client.log_usage_failed", error=str(exc))
