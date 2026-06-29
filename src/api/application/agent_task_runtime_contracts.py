"""Agent task runtime contracts detached from the inbox transport.

The runtime layer consumes pointer-only task requests and returns typed visible
reply data. It must not know how inbox messages are claimed, acknowledged, or
written back to the task thread.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from api.application.agent_action_proposals import AgentActionProposalDraft
from api.application.agent_tasks import (
    AGENT_TASK_FOLLOWUP_SCHEMA_VERSION,
    AgentTaskMessageKind,
    AgentTaskStatus,
)


@dataclass(frozen=True, slots=True)
class AgentTaskRuntimeRequest:
    """Pointer-only request passed to an internal agent runtime."""

    task_id: UUID
    message_id: UUID
    program_id: UUID
    campaign_id: UUID | None
    correlation_id: UUID | None
    target_agent: str
    schema_version: str
    body_excerpt: str
    body_hash: str | None
    context_refs: tuple[dict, ...] = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)
    source: str | None = None


@dataclass(frozen=True, slots=True)
class AgentTaskRuntimeResult:
    """Visible reply produced by an internal agent runtime."""

    agent_key: str
    body: str
    message_kind: AgentTaskMessageKind = AgentTaskMessageKind.NOTE
    status: AgentTaskStatus = AgentTaskStatus.WAITING
    artifact_refs: tuple[dict, ...] = field(default_factory=tuple)
    fact_refs: tuple[dict, ...] = field(default_factory=tuple)
    graph_refs: tuple[dict, ...] = field(default_factory=tuple)
    action_refs: tuple[dict, ...] = field(default_factory=tuple)
    proposal_refs: tuple[dict, ...] = field(default_factory=tuple)
    decision_refs: tuple[dict, ...] = field(default_factory=tuple)
    proposal_drafts: tuple[AgentActionProposalDraft, ...] = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)


class AgentTaskRuntime(Protocol):
    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult: ...


class BoundedAgentTaskRuntime:
    """Small deterministic fallback runtime for live task threads."""

    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
        return AgentTaskRuntimeResult(
            agent_key=agent_task_runtime_agent_key(request.target_agent),
            body=self._reply_body(request),
            message_kind=AgentTaskMessageKind.QUESTION,
            status=AgentTaskStatus.WAITING,
            metadata={
                "runtime": "bounded-agent-task-runtime.v1",
                "source_message_id": str(request.message_id),
                "boundary": {
                    "tool_execution": "forbidden_from_agent_task_runtime",
                    "next_step": "agent_may_propose_bounded_action_request",
                },
            },
        )

    @staticmethod
    def _reply_body(request: AgentTaskRuntimeRequest) -> str:
        body = request.body_excerpt.strip()
        if not body:
            body = "Промт принят, но текст пуст после санитарной обработки."
        if request.schema_version == AGENT_TASK_FOLLOWUP_SCHEMA_VERSION:
            prefix = "Принял уточнение по задаче."
        else:
            prefix = "Принял задачу в работу."
        return (
            f"{prefix} Я буду работать только с безопасными ссылками на контекст и "
            "не буду запускать инструменты из промта напрямую. "
            "Следующий результат появится здесь как находка, вопрос или proposal.\n\n"
            f"Кратко понял запрос: {body[:700]}"
        )


def agent_task_runtime_agent_key(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-").replace("_", "-")
    return normalized or "coordinator"
