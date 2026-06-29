"""Typed result ingest boundary for external LangGraph agent-task workers.

LangGraph owns agent workflow execution, threads, checkpoints, and streaming.
The API/domain layer owns the durable product output: visible task messages,
agent proposals, feedback, and action-control boundaries. This module is the
small bridge between those two worlds: a worker posts one typed runtime result,
and the domain layer persists the message/proposals and optionally acks the
inbox handoff only after the output is durable.

This boundary still does not execute tools. Agent output may create advisory
proposals, but any real action must be accepted through ActionService, policy,
scope, approval, and budget.
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.application.agent_action_proposals import (
    AgentActionProposalDraft,
    AgentActionProposalWriter,
    proposal_record_ref,
)
from api.application.agent_tasks import (
    AgentTaskAgentReplyRequest,
    AgentTaskMessageKind,
    AgentTaskMessageRecord,
    AgentTaskService,
    AgentTaskStatus,
)


AGENT_TASK_RUNTIME_RESULT_SCHEMA_VERSION = "agent-task-runtime-result.v1"


class AgentTaskRuntimeResultIngestRequest(BaseModel):
    """Typed output emitted by an internal LangGraph task worker.

    ``source_message_id`` is the human prompt/follow-up message that produced
    this runtime result. It is used as provenance for any proposal drafts.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=AGENT_TASK_RUNTIME_RESULT_SCHEMA_VERSION)
    task_id: UUID
    source_message_id: UUID
    program_id: UUID
    agent_key: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=12_000)
    campaign_id: UUID | None = None
    inbox_message_id: UUID | None = None
    message_kind: AgentTaskMessageKind = AgentTaskMessageKind.NOTE
    status: AgentTaskStatus | None = None
    source: str = Field(default="langgraph-agent-worker", min_length=1, max_length=100)
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    fact_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_refs: list[dict[str, Any]] = Field(default_factory=list)
    action_refs: list[dict[str, Any]] = Field(default_factory=list)
    proposal_refs: list[dict[str, Any]] = Field(default_factory=list)
    decision_refs: list[dict[str, Any]] = Field(default_factory=list)
    proposal_drafts: list[AgentActionProposalDraft] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ack_inbox: bool = True

    @field_validator("schema_version")
    @classmethod
    def schema_version_must_match(cls, value: str) -> str:
        if value != AGENT_TASK_RUNTIME_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {AGENT_TASK_RUNTIME_RESULT_SCHEMA_VERSION}"
            )
        return value

    @field_validator("agent_key", "body", "source")
    @classmethod
    def normalize_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class AgentTaskRuntimeResultIngested(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    source_message_id: UUID
    reply_message: AgentTaskMessageRecord
    proposal_refs: list[dict[str, Any]] = Field(default_factory=list)
    proposal_count: int = 0
    inbox_message_id: UUID | None = None
    inbox_acknowledged: bool = False


class AgentTaskRuntimeResultAckStore(Protocol):
    async def ack_inbox_message(self, *, message_id: Any) -> None: ...


class AgentTaskRuntimeResultIngestService:
    """Persist typed LangGraph worker output into domain read/write models."""

    def __init__(
        self,
        *,
        task_service: AgentTaskService,
        proposal_writer: AgentActionProposalWriter | None = None,
        ack_store: AgentTaskRuntimeResultAckStore | None = None,
    ) -> None:
        self.task_service = task_service
        self.proposal_writer = proposal_writer
        self.ack_store = ack_store

    async def ingest(
        self,
        request: AgentTaskRuntimeResultIngestRequest,
    ) -> AgentTaskRuntimeResultIngested:
        created_proposal_refs = await self._write_agent_proposals(request)
        proposal_refs = [*request.proposal_refs, *created_proposal_refs]
        reply = await self.task_service.append_agent_reply(
            task_id=request.task_id,
            request=AgentTaskAgentReplyRequest(
                agent_key=request.agent_key,
                body=request.body,
                message_kind=request.message_kind,
                status=request.status,
                source=request.source,
                artifact_refs=request.artifact_refs,
                fact_refs=request.fact_refs,
                graph_refs=request.graph_refs,
                action_refs=request.action_refs,
                proposal_refs=proposal_refs,
                decision_refs=request.decision_refs,
                metadata={
                    **request.metadata,
                    "agent_task_runtime_result_schema_version": request.schema_version,
                    "agent_task_source_message_id": str(request.source_message_id),
                    "agent_task_inbox_message_id": (
                        str(request.inbox_message_id) if request.inbox_message_id else None
                    ),
                    "agent_action_proposals_created": len(created_proposal_refs),
                    "runtime_result_boundary": {
                        "owner": "domain-control-plane",
                        "runtime_owner": "langgraph",
                        "tool_execution": "forbidden_from_runtime_result_ingest",
                        "action_service_required": True,
                    },
                },
            ),
        )
        inbox_acknowledged = await self._ack_inbox_if_requested(request)
        return AgentTaskRuntimeResultIngested(
            task_id=request.task_id,
            source_message_id=request.source_message_id,
            reply_message=reply,
            proposal_refs=proposal_refs,
            proposal_count=len(created_proposal_refs),
            inbox_message_id=request.inbox_message_id,
            inbox_acknowledged=inbox_acknowledged,
        )

    async def _write_agent_proposals(
        self,
        request: AgentTaskRuntimeResultIngestRequest,
    ) -> list[dict[str, Any]]:
        if not request.proposal_drafts or self.proposal_writer is None:
            return []
        records = await self.proposal_writer.write_agent_task_proposals(
            program_id=request.program_id,
            campaign_id=request.campaign_id,
            task_id=request.task_id,
            source_message_id=request.source_message_id,
            agent_key=request.agent_key,
            drafts=tuple(request.proposal_drafts),
        )
        return [proposal_record_ref(record) for record in records]

    async def _ack_inbox_if_requested(
        self,
        request: AgentTaskRuntimeResultIngestRequest,
    ) -> bool:
        if not request.ack_inbox or request.inbox_message_id is None or self.ack_store is None:
            return False
        await self.ack_store.ack_inbox_message(message_id=request.inbox_message_id)
        return True
