"""Legacy/local bridge from task handoff messages to visible task threads.

This module is now the transport adapter only. Runtime contracts live in
``agent_task_runtime_contracts`` so LangGraph/runtime code does not depend on the
legacy inbox processor.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.agent_action_proposals import (
    AgentActionProposalWriter,
    proposal_record_ref,
)
from api.application.agent_task_inbox_bridge_models import (
    AgentTaskInboxBridgeResult,
    AgentTaskInboxProcessorSweep,
    AgentTaskInboxStore,
)
from api.application.agent_task_inbox_payload import runtime_request_from_agent_task_message
from api.application.agent_task_runtime_contracts import (
    AgentTaskRuntime,
    AgentTaskRuntimeRequest,
    AgentTaskRuntimeResult,
    BoundedAgentTaskRuntime,
)
from api.application.agent_tasks import (
    AGENT_TASK_PROMPT_MESSAGE_TYPE,
    AgentTaskAgentReplyRequest,
    AgentTaskService,
)


class AgentTaskInboxBridge:
    """Append one claimed agent-task inbox message to the live task thread."""

    def __init__(
        self,
        *,
        runtime: AgentTaskRuntime,
        task_service: AgentTaskService,
        inbox_store: AgentTaskInboxStore,
        proposal_writer: AgentActionProposalWriter | None = None,
    ) -> None:
        self.runtime = runtime
        self.task_service = task_service
        self.inbox_store = inbox_store
        self.proposal_writer = proposal_writer

    async def handoff(self, message: dict[str, Any]) -> AgentTaskInboxBridgeResult:
        message_id = _message_id(message)
        if message.get("message_type") != AGENT_TASK_PROMPT_MESSAGE_TYPE:
            await self.inbox_store.ack_inbox_message(message_id=message_id)
            return AgentTaskInboxBridgeResult(
                message_id=message_id,
                task_id=None,
                outcome="skipped",
                acknowledged=True,
                reason_code="unsupported_message_type",
            )

        request = runtime_request_from_agent_task_message(message)
        result = await self.runtime.handle(request)
        created_proposal_refs = await self._write_agent_proposals(request=request, result=result)
        reply = await self.task_service.append_agent_reply(
            task_id=request.task_id,
            request=_agent_reply_request(
                result=result,
                message_id=message_id,
                created_proposal_refs=created_proposal_refs,
            ),
        )
        await self.inbox_store.ack_inbox_message(message_id=message_id)
        return AgentTaskInboxBridgeResult(
            message_id=message_id,
            task_id=request.task_id,
            outcome="processed",
            acknowledged=True,
            reply_message_id=reply.message_id,
        )

    async def _write_agent_proposals(
        self,
        *,
        request: AgentTaskRuntimeRequest,
        result: AgentTaskRuntimeResult,
    ) -> tuple[dict[str, Any], ...]:
        if not result.proposal_drafts or self.proposal_writer is None:
            return tuple()
        records = await self.proposal_writer.write_agent_task_proposals(
            program_id=request.program_id,
            campaign_id=request.campaign_id,
            task_id=request.task_id,
            source_message_id=request.message_id,
            agent_key=result.agent_key,
            drafts=tuple(result.proposal_drafts),
        )
        return tuple(proposal_record_ref(record) for record in records)


def _agent_reply_request(
    *,
    result: AgentTaskRuntimeResult,
    message_id: Any,
    created_proposal_refs: tuple[dict[str, Any], ...],
) -> AgentTaskAgentReplyRequest:
    proposal_refs = tuple(result.proposal_refs) + tuple(created_proposal_refs)
    return AgentTaskAgentReplyRequest(
        agent_key=result.agent_key,
        body=result.body,
        message_kind=result.message_kind,
        status=result.status,
        source="agent-task-runtime",
        artifact_refs=list(result.artifact_refs),
        fact_refs=list(result.fact_refs),
        graph_refs=list(result.graph_refs),
        action_refs=list(result.action_refs),
        proposal_refs=list(proposal_refs),
        decision_refs=list(result.decision_refs),
        metadata={
            **result.metadata,
            "agent_task_inbox_message_id": str(message_id),
            "agent_action_proposals_created": len(created_proposal_refs),
            "proposal_boundary": {
                "tool_execution": "forbidden_from_agent_reply",
                "action_service_required": True,
            },
        },
    )


def _message_id(message: dict[str, Any]) -> UUID:
    value = message.get("id")
    if value is None:
        raise ValueError("id is required for agent task inbox bridge")
    return value if isinstance(value, UUID) else UUID(str(value))


# Compatibility exports for existing tests/imports. New runtime code should import
# contracts from agent_task_runtime_contracts and processor code from
# agent_task_inbox_processor.
from api.application.agent_task_inbox_processor import AgentTaskInboxProcessor  # noqa: E402

__all__ = [
    "AgentTaskInboxBridge",
    "AgentTaskInboxBridgeResult",
    "AgentTaskInboxProcessor",
    "AgentTaskInboxProcessorSweep",
    "AgentTaskInboxStore",
    "AgentTaskRuntime",
    "AgentTaskRuntimeRequest",
    "AgentTaskRuntimeResult",
    "BoundedAgentTaskRuntime",
    "runtime_request_from_agent_task_message",
]
