"""vLLM client — sends OpenAI-compatible chat completion requests to a local vLLM server.

Implements the LLMGateway Protocol defined in domain/interfaces/services.py.

Model tier: "local"
Default endpoint: http://localhost:8080/v1/chat/completions
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from app.domain.exceptions import ServiceUnavailableError

logger = structlog.get_logger(__name__)

_DEFAULT_ENDPOINT = "http://localhost:8080/v1/chat/completions"
_REQUEST_TIMEOUT = 120.0  # vLLM inference can be slow on first call


class VllmClient:
    """Async HTTP client for a locally-running vLLM server (OpenAI-compatible API)."""

    def __init__(
        self,
        model: str,
        endpoint: str = _DEFAULT_ENDPOINT,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> None:
        self._model = model
        self._endpoint = endpoint
        self._timeout = timeout

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
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("vllm_client.http_error", error=str(exc), model=self._model)
            raise ServiceUnavailableError(f"vLLM request failed: {exc}") from exc

        data = response.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise ServiceUnavailableError(f"vLLM response missing expected fields: {exc}") from exc

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system: str = "",
        max_tokens: int = 2048,
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
        )
        try:
            # Strip markdown code fences if the model wrapped the JSON
            stripped = text.strip()
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                stripped = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return dict(json.loads(stripped))  # type: ignore[arg-type]
        except json.JSONDecodeError as exc:
            raise ServiceUnavailableError(
                f"vLLM returned invalid JSON: {exc}\nRaw: {text[:200]}"
            ) from exc
