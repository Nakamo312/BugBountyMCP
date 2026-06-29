"""User-facing agent task prompts.

This boundary lets a human steer agents with bounded prompts without giving the
prompt direct tool-execution power. A prompt becomes a durable product task and
visible task-thread message; agent workflow execution belongs to LangGraph. Any
tool action proposed by the agent must still go through ActionService, policy,
scope, approval, and budget.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.application.research.sanitizer import sanitize_json, sanitize_text


AGENT_TASK_PROMPT_MESSAGE_TYPE = "agent.task.prompted"
AGENT_TASK_PROMPT_SCHEMA_VERSION = "agent-task-prompt.v1"
AGENT_TASK_REPLY_SCHEMA_VERSION = "agent-task-reply.v1"
AGENT_TASK_FOLLOWUP_SCHEMA_VERSION = "agent-task-followup.v1"
AGENT_TASK_PROMPT_MAX_CHARS = 12_000
AGENT_TASK_PROMPT_EXCERPT_CHARS = 4_000


class AgentTaskStatus(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTaskMessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AgentTaskMessageKind(str, Enum):
    NOTE = "note"
    FINDING = "finding"
    PROPOSAL = "proposal"
    QUESTION = "question"
    DECISION = "decision"
    ERROR = "error"


class AgentTaskPromptRequest(BaseModel):
    """A human prompt that should become a bounded agent task."""

    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    prompt: str = Field(min_length=1, max_length=AGENT_TASK_PROMPT_MAX_CHARS)
    created_by: str = Field(default="human", min_length=1, max_length=150)
    target_agent: str = Field(default="coordinator", min_length=1, max_length=100)
    campaign_id: UUID | None = None
    correlation_id: UUID = Field(default_factory=uuid4)
    source: str = Field(default="ui", min_length=1, max_length=100)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must not be blank")
        return stripped

    @field_validator("created_by", "target_agent", "source")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class AgentTaskFollowupRequest(BaseModel):
    """A human follow-up message inside an existing agent task."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=AGENT_TASK_PROMPT_MAX_CHARS)
    created_by: str = Field(default="human", min_length=1, max_length=150)
    source: str = Field(default="ui", min_length=1, max_length=100)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("body must not be blank")
        return stripped

    @field_validator("created_by", "source")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class AgentTaskAgentReplyRequest(BaseModel):
    """An internal agent response visible in the task thread."""

    model_config = ConfigDict(extra="forbid")

    agent_key: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=AGENT_TASK_PROMPT_MAX_CHARS)
    message_kind: AgentTaskMessageKind = AgentTaskMessageKind.NOTE
    status: AgentTaskStatus | None = None
    source: str = Field(default="agent", min_length=1, max_length=100)
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    fact_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_refs: list[dict[str, Any]] = Field(default_factory=list)
    action_refs: list[dict[str, Any]] = Field(default_factory=list)
    proposal_refs: list[dict[str, Any]] = Field(default_factory=list)
    decision_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_key", "body", "source")
    @classmethod
    def normalize_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class AgentTaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    correlation_id: UUID
    status: AgentTaskStatus
    target_agent: str
    title: str
    prompt_excerpt: str
    prompt_hash: str
    created_by: str
    source: str
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    inbox_message_id: UUID | None = None


class AgentTaskMessageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    task_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    correlation_id: UUID
    role: AgentTaskMessageRole
    message_kind: AgentTaskMessageKind = AgentTaskMessageKind.NOTE
    agent_key: str | None = None
    body: str
    body_hash: str
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    fact_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_refs: list[dict[str, Any]] = Field(default_factory=list)
    action_refs: list[dict[str, Any]] = Field(default_factory=list)
    proposal_refs: list[dict[str, Any]] = Field(default_factory=list)
    decision_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentTaskCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: AgentTaskRecord
    first_message: AgentTaskMessageRecord
    inbox_message_id: UUID | None = None


class AgentTaskStore(Protocol):
    async def create_prompt_task(
        self,
        *,
        request: AgentTaskPromptRequest,
        task_id: UUID,
        message_id: UUID,
        title: str,
        prompt_excerpt: str,
        prompt_hash: str,
        sanitized_context_refs: list[dict[str, Any]],
        sanitized_metadata: dict[str, Any],
        inbox_payload: dict[str, Any],
        dedupe_key: str,
    ) -> AgentTaskCreated: ...

    async def list_tasks(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        status: AgentTaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskRecord]: ...

    async def list_task_messages(
        self,
        *,
        task_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskMessageRecord]: ...

    async def append_followup_message(
        self,
        *,
        task_id: UUID,
        message_id: UUID,
        request: AgentTaskFollowupRequest,
        body: str,
        body_hash: str,
        sanitized_context_refs: list[dict[str, Any]],
        sanitized_metadata: dict[str, Any],
        inbox_payload: dict[str, Any],
        dedupe_key: str,
    ) -> AgentTaskMessageRecord: ...

    async def append_agent_reply(
        self,
        *,
        task_id: UUID,
        message_id: UUID,
        request: AgentTaskAgentReplyRequest,
        body: str,
        body_hash: str,
        sanitized_refs: dict[str, list[dict[str, Any]]],
        sanitized_metadata: dict[str, Any],
    ) -> AgentTaskMessageRecord: ...


class AgentTaskService:
    """Create and read user-facing agent tasks.

    This service intentionally creates product-visible work for agents, not
    tool actions. LangGraph should own runtime thread execution; this service
    persists domain task state and handoff metadata. Agent output may later
    become a proposal or an ActionRequest, but only through the existing safety
    boundary.
    """

    def __init__(self, store: AgentTaskStore) -> None:
        self.store = store

    async def create_prompt_task(self, request: AgentTaskPromptRequest) -> AgentTaskCreated:
        sanitized = sanitize_text(
            request.prompt,
            limit=AGENT_TASK_PROMPT_MAX_CHARS,
        )
        prompt_excerpt = sanitized.safe_excerpt[:AGENT_TASK_PROMPT_EXCERPT_CHARS]
        prompt_hash = sanitized.normalized_content_hash
        task_id = uuid4()
        message_id = uuid4()
        title = self._title_from_prompt(prompt_excerpt)
        sanitized_context_refs = sanitize_json(request.context_refs)
        sanitized_metadata = sanitize_json(request.metadata)
        dedupe_key = f"agent-task:{task_id}:prompted"
        inbox_payload = {
            "schema_version": AGENT_TASK_PROMPT_SCHEMA_VERSION,
            "task_id": str(task_id),
            "message_id": str(message_id),
            "program_id": str(request.program_id),
            "campaign_id": str(request.campaign_id) if request.campaign_id else None,
            "correlation_id": str(request.correlation_id),
            "target_agent": request.target_agent,
            "created_by": request.created_by,
            "source": request.source,
            "prompt_excerpt": prompt_excerpt,
            "prompt_hash": prompt_hash,
            "redaction": {
                "sanitizer_version": sanitized.sanitizer_version,
                "redaction_policy_version": sanitized.redaction_policy_version,
                "sensitivity_level": sanitized.sensitivity_level,
                "rules": list(sanitized.redaction_rules_triggered),
            },
            "context_refs": sanitized_context_refs,
            "metadata": sanitized_metadata,
            "boundary": {
                "tool_execution": "forbidden_from_prompt",
                "next_step": "agent_may_propose_bounded_action_request",
            },
        }
        inbox_payload = {key: value for key, value in inbox_payload.items() if value is not None}
        return await self.store.create_prompt_task(
            request=request,
            task_id=task_id,
            message_id=message_id,
            title=title,
            prompt_excerpt=prompt_excerpt,
            prompt_hash=prompt_hash,
            sanitized_context_refs=sanitized_context_refs,
            sanitized_metadata=sanitized_metadata,
            inbox_payload=inbox_payload,
            dedupe_key=dedupe_key,
        )

    async def list_tasks(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        status: AgentTaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskRecord]:
        return await self.store.list_tasks(
            program_id=program_id,
            campaign_id=campaign_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_task_messages(
        self,
        *,
        task_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskMessageRecord]:
        return await self.store.list_task_messages(
            task_id=task_id,
            limit=limit,
            offset=offset,
        )

    async def append_followup_message(
        self,
        *,
        task_id: UUID,
        request: AgentTaskFollowupRequest,
    ) -> AgentTaskMessageRecord:
        sanitized = sanitize_text(
            request.body,
            limit=AGENT_TASK_PROMPT_MAX_CHARS,
        )
        body = sanitized.safe_excerpt[:AGENT_TASK_PROMPT_MAX_CHARS]
        message_id = uuid4()
        body_digest = sanitized.normalized_content_hash
        sanitized_context_refs = sanitize_json(request.context_refs)
        sanitized_metadata = sanitize_json(request.metadata)
        dedupe_key = f"agent-task:{task_id}:followup:{message_id}"
        inbox_payload = {
            "schema_version": AGENT_TASK_FOLLOWUP_SCHEMA_VERSION,
            "task_id": str(task_id),
            "message_id": str(message_id),
            "created_by": request.created_by,
            "source": request.source,
            "body_excerpt": body,
            "body_hash": body_digest,
            "redaction": {
                "sanitizer_version": sanitized.sanitizer_version,
                "redaction_policy_version": sanitized.redaction_policy_version,
                "sensitivity_level": sanitized.sensitivity_level,
                "rules": list(sanitized.redaction_rules_triggered),
            },
            "context_refs": sanitized_context_refs,
            "metadata": sanitized_metadata,
            "boundary": {
                "tool_execution": "forbidden_from_prompt",
                "next_step": "agent_may_reply_or_propose_bounded_action_request",
            },
        }
        return await self.store.append_followup_message(
            task_id=task_id,
            message_id=message_id,
            request=request,
            body=body,
            body_hash=body_digest,
            sanitized_context_refs=sanitized_context_refs,
            sanitized_metadata=sanitized_metadata,
            inbox_payload=inbox_payload,
            dedupe_key=dedupe_key,
        )

    async def append_agent_reply(
        self,
        *,
        task_id: UUID,
        request: AgentTaskAgentReplyRequest,
    ) -> AgentTaskMessageRecord:
        sanitized = sanitize_text(
            request.body,
            limit=AGENT_TASK_PROMPT_MAX_CHARS,
        )
        body = sanitized.safe_excerpt[:AGENT_TASK_PROMPT_MAX_CHARS]
        message_id = uuid4()
        sanitized_refs = {
            "artifact_refs": sanitize_json(request.artifact_refs),
            "fact_refs": sanitize_json(request.fact_refs),
            "graph_refs": sanitize_json(request.graph_refs),
            "action_refs": sanitize_json(request.action_refs),
            "proposal_refs": sanitize_json(request.proposal_refs),
            "decision_refs": sanitize_json(request.decision_refs),
        }
        sanitized_metadata = sanitize_json(
            {
                **request.metadata,
                "source": request.source,
                "redaction": {
                    "sanitizer_version": sanitized.sanitizer_version,
                    "redaction_policy_version": sanitized.redaction_policy_version,
                    "sensitivity_level": sanitized.sensitivity_level,
                    "rules": list(sanitized.redaction_rules_triggered),
                },
                "boundary": {
                    "tool_execution": "forbidden_from_agent_reply",
                    "next_step": "operator_or_scheduler_must_create_action_request",
                },
            }
        )
        return await self.store.append_agent_reply(
            task_id=task_id,
            message_id=message_id,
            request=request,
            body=body,
            body_hash=sanitized.normalized_content_hash,
            sanitized_refs=sanitized_refs,
            sanitized_metadata=sanitized_metadata,
        )

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), "Agent task")
        title = " ".join(first_line.split())
        return title[:120] or "Agent task"


def body_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
