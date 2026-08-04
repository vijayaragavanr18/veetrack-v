"""Use case: The Executive PR Agent reviews storylines and drafts responses."""

from __future__ import annotations

from typing import Any

import structlog

from app.application.use_cases.shared.agent_loop import (
    AgentDidNotConvergeError,
    AgentLoop,
    ToolCallable,
)
from app.domain.interfaces.services import LLMGateway

logger = structlog.get_logger(__name__)

class ExecutivePRAgent:
    """Agent that acts as Chief Communications Officer, drafting alerts and responses.
    
    Parameters
    ----------
    gateway:
        LLMGateway used to run the agent.
    tools:
        Dictionary of tools (get_storyline_context, get_company_guidelines) 
        injected by the container.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        tools: dict[str, ToolCallable] | None = None,
    ) -> None:
        self._gateway = gateway
        self._tools = tools or {}

    async def execute(self, storyline_id: str, trigger_event: str) -> dict[str, Any]:
        """Run the Executive PR agent to handle a developing storyline."""
        from app.application.agents.executive_pr.prompt import (
            SYSTEM_PROMPT,
            TOOL_NAMES,
            validate_final_answer,
        )

        loop = AgentLoop(
            gateway=self._gateway,
            system_prompt=SYSTEM_PROMPT,
            tool_names=TOOL_NAMES,
            tools=self._tools,
            max_iterations=5,
            max_tokens_per_step=1024,
            agent_name="executive_pr_agent",
        )

        initial_msg = (
            f"An urgent trigger event has occurred for storyline {storyline_id!r}.\n\n"
            f"Trigger Event: {trigger_event!r}\n\n"
            f"Use your tools to gather the full context of the storyline and the "
            f"company's PR guidelines. Then, draft an action plan including a Slack alert, "
            f"a mitigation strategy, and a drafted public statement."
        )

        try:
            loop_result = await loop.run(initial_msg, run_id=f"exec_pr:{storyline_id[:8]}")
        except AgentDidNotConvergeError as exc:
            logger.warning("exec_pr_agent.did_not_converge", storyline=storyline_id, error=str(exc))
            return {
                "risk_assessment": "high",
                "slack_alert_draft": f"URGENT: Agent timeout while analyzing {trigger_event}. Manual review required.",
                "mitigation_strategy": "N/A",
                "draft_statement": "N/A",
                "reasoning": "Agent loop exhausted."
            }
        except Exception as exc:
            logger.error("exec_pr_agent.failed", storyline=storyline_id, error=str(exc))
            return {
                "risk_assessment": "high",
                "slack_alert_draft": f"ERROR: System failed to analyze {trigger_event}.",
                "mitigation_strategy": "N/A",
                "draft_statement": "N/A",
                "reasoning": str(exc)
            }

        final = loop_result.final_step
        try:
            validate_final_answer(final)
        except ValueError as ve:
            logger.warning("exec_pr_agent.invalid_final_answer", storyline=storyline_id, error=str(ve))
            return {
                "risk_assessment": "high",
                "slack_alert_draft": "ERROR: Invalid plan generated.",
                "mitigation_strategy": "N/A",
                "draft_statement": "N/A",
                "reasoning": "Parse error."
            }

        return {
            "risk_assessment": final.get("risk_assessment"),
            "slack_alert_draft": final.get("slack_alert_draft"),
            "mitigation_strategy": final.get("mitigation_strategy"),
            "draft_statement": final.get("draft_statement"),
            "reasoning": final.get("reasoning"),
        }
