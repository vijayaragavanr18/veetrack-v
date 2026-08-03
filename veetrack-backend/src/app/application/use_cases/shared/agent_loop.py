"""Generic bounded ReAct loop engine.

Shared by RecommendationAgent (Phase 17) and AlertAgent (Phase 24). Do not fork a
second copy — import this directly from both call sites.

The loop runs Reason → Act → Observe cycles until the model produces a response
matching ``final_answer_type`` or MAX_ITERATIONS is reached.

Design constraints:
  - Zero infrastructure imports.  All I/O is via the injected LLMGateway and
    tool callables.
  - Every model response is validated against a caller-supplied JSON schema
    before acting on it, with one retry on parse failure.
  - Tool results are capped at ``max_tool_result_chars`` to keep the context
    window bounded across iterations.
  - On loop exhaustion, raises ``AgentDidNotConvergeError`` so callers can
    implement their own fallback strategy.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

# Public alias — callers import this name.
ToolCallable = Callable[[dict[str, Any]], Awaitable[str]]

DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_TOOL_RESULT_CHARS = 600


# ── Exceptions ────────────────────────────────────────────────────────────────


class AgentDidNotConvergeError(Exception):
    """Raised when the loop exhausts MAX_ITERATIONS without a final_answer step."""


# ── Trace entries ─────────────────────────────────────────────────────────────


@dataclass
class TraceEntry:
    iteration: int
    type: str  # "tool_call" | "observation" | "final_answer" | "error"
    content: dict[str, Any]
    elapsed_ms: int = 0


@dataclass
class LoopResult:
    """Raw output from AgentLoop.run()."""

    final_step: dict[str, Any]
    reasoning: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    iterations_used: int = 0


# ── JSON helpers ──────────────────────────────────────────────────────────────


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from a model response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text


def parse_json_response(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON; raises ValueError on failure."""
    try:
        parsed = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Response is not a JSON object")
    return parsed  # type: ignore[return-value]


def validate_step(data: dict[str, Any], tool_names: set[str]) -> dict[str, Any]:
    """Structural validation of a single ReAct step; raises ValueError on violation."""
    step_type = data.get("type")
    if step_type not in ("tool_call", "final_answer"):
        raise ValueError(
            f'`type` must be "tool_call" or "final_answer", got {step_type!r}'
        )
    if step_type == "tool_call":
        if "tool" not in data:
            raise ValueError('tool_call missing required field "tool"')
        if data["tool"] not in tool_names:
            raise ValueError(
                f'Unknown tool {data["tool"]!r}. Valid: {sorted(tool_names)}'
            )
        if not isinstance(data.get("args"), dict):
            raise ValueError('"args" must be an object')
    return data


# ── Core loop ─────────────────────────────────────────────────────────────────


class AgentLoop:
    """Generic bounded ReAct loop.

    Parameters
    ----------
    gateway:
        LLMGateway — used for ``complete()`` calls.
    system_prompt:
        System-level instructions sent on every iteration.
    tool_names:
        Set of valid tool names.  Validated against every ``tool_call`` step.
    tools:
        Mapping of tool_name → async callable.  Missing tools return a
        "not available" observation rather than raising.
    max_iterations:
        Hard cap on the number of Reason/Act cycles.
    max_tokens_per_step:
        Token budget passed to the LLM on each ``complete()`` call.
    max_tool_result_chars:
        Observation strings are truncated to this length to keep the context
        window from ballooning across iterations.
    agent_name:
        Short label used in structured log fields.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        system_prompt: str,
        tool_names: set[str],
        tools: dict[str, ToolCallable],
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_tokens_per_step: int = 600,
        max_tool_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
        agent_name: str = "agent",
    ) -> None:
        self._gateway = gateway
        self._system = system_prompt
        self._tool_names = tool_names
        self._tools = tools
        self._max_iterations = max_iterations
        self._max_tokens = max_tokens_per_step
        self._max_obs_chars = max_tool_result_chars
        self._agent_name = agent_name

    async def run(self, initial_user_message: str, run_id: str = "") -> LoopResult:
        """Execute the ReAct loop starting from *initial_user_message*.

        Parameters
        ----------
        initial_user_message:
            The first user turn (contains the task + context).
        run_id:
            Opaque identifier logged on every iteration (story_id, alert_id, …).

        Returns
        -------
        LoopResult
            Contains the ``final_step`` dict, extracted ``reasoning`` string,
            full ``trace`` list, and ``iterations_used`` count.

        Raises
        ------
        AgentDidNotConvergeError
            If the loop exhausts ``max_iterations`` without a ``final_answer`` step.
        """
        messages: list[dict[str, str]] = [
            {"role": "user", "content": initial_user_message}
        ]
        trace: list[TraceEntry] = []

        for iteration in range(1, self._max_iterations + 1):
            t0 = time.monotonic()

            full_prompt = "\n\n".join(
                f"[{m['role'].upper()}]\n{m['content']}" for m in messages
            )
            raw = await self._gateway.complete(
                full_prompt,
                system=self._system,
                max_tokens=self._max_tokens,
                temperature=0.0,
            )
            elapsed = int((time.monotonic() - t0) * 1000)

            # Parse + validate — retry once on failure
            try:
                step = validate_step(
                    parse_json_response(raw), self._tool_names
                )
            except ValueError as parse_err:
                trace.append(
                    TraceEntry(
                        iteration=iteration,
                        type="error",
                        content={"raw": raw[:200], "error": str(parse_err)},
                        elapsed_ms=elapsed,
                    )
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your last response was invalid: {parse_err}. "
                            "Please respond with a valid JSON object matching one "
                            "of the two allowed shapes."
                        ),
                    }
                )
                logger.warning(
                    f"{self._agent_name}.parse_error",
                    run_id=run_id,
                    iteration=iteration,
                    error=str(parse_err),
                )
                continue

            step_type = step["type"]

            if step_type == "tool_call":
                tool_name = step["tool"]
                tool_args = step["args"]
                reasoning = step.get("reasoning", "")

                trace.append(
                    TraceEntry(
                        iteration=iteration,
                        type="tool_call",
                        content={
                            "tool": tool_name,
                            "args": tool_args,
                            "reasoning": reasoning,
                        },
                        elapsed_ms=elapsed,
                    )
                )

                tool_fn = self._tools.get(tool_name)
                if tool_fn is None:
                    observation = f"Tool '{tool_name}' is not available in this environment."
                else:
                    try:
                        observation = await tool_fn(tool_args)
                        observation = observation[: self._max_obs_chars]
                    except Exception as tool_err:
                        observation = f"Tool error: {tool_err}"
                        logger.warning(
                            f"{self._agent_name}.tool_error",
                            run_id=run_id,
                            tool=tool_name,
                            error=str(tool_err),
                        )

                trace.append(
                    TraceEntry(
                        iteration=iteration,
                        type="observation",
                        content={"tool": tool_name, "result": observation},
                        elapsed_ms=0,
                    )
                )
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool result for {tool_name}:\n{observation}\n\nContinue reasoning."
                        ),
                    }
                )
                logger.debug(
                    f"{self._agent_name}.tool_called",
                    run_id=run_id,
                    iteration=iteration,
                    tool=tool_name,
                )

            else:  # final_answer
                reasoning = step.get("reasoning", "")
                trace.append(
                    TraceEntry(
                        iteration=iteration,
                        type="final_answer",
                        content={"reasoning": reasoning},
                        elapsed_ms=elapsed,
                    )
                )
                logger.info(
                    f"{self._agent_name}.converged",
                    run_id=run_id,
                    iterations=iteration,
                    model=self._gateway.model_name,
                )
                return LoopResult(
                    final_step=dict(step),
                    reasoning=reasoning,
                    trace=[vars(e) for e in trace],
                    iterations_used=iteration,
                )

        raise AgentDidNotConvergeError(
            f"{self._agent_name} exhausted {self._max_iterations} iterations "
            f"without a final_answer (run_id={run_id!r})"
        )
