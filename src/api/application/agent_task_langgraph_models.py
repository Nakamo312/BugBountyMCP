"""Typed interfaces and thread identity for agent-task LangGraph runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypedDict
from uuid import UUID

from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest
from api.application.agent_task_langgraph_helpers import safe_checkpoint_namespace


class AgentTaskContextReader(Protocol):
    """Read bounded, pointer-only context for an agent task runtime."""

    async def read(self, request: AgentTaskRuntimeRequest) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AgentTaskLangGraphThreadRef:
    """Deterministic LangGraph thread identity for one visible agent task."""

    task_id: UUID
    thread_id: str
    checkpoint_ns: str = "agent-task"

    def config(self) -> dict[str, dict[str, str]]:
        return {
            "configurable": {
                "thread_id": self.thread_id,
                "checkpoint_ns": self.checkpoint_ns,
            }
        }

    def to_metadata(self) -> dict[str, str]:
        return {
            "thread_id": self.thread_id,
            "checkpoint_ns": self.checkpoint_ns,
            "owner": "langgraph",
            "domain_task_id": str(self.task_id),
        }


def agent_task_langgraph_thread_ref(
    task_id: UUID,
    *,
    checkpoint_ns: str = "agent-task",
) -> AgentTaskLangGraphThreadRef:
    return AgentTaskLangGraphThreadRef(
        task_id=task_id,
        thread_id=f"agent-task:{task_id}",
        checkpoint_ns=safe_checkpoint_namespace(checkpoint_ns),
    )


class AgentTaskGraphRunner(Protocol):
    """Internal LangGraph runner used behind the AgentTaskRuntime protocol."""

    async def ainvoke(
        self,
        *,
        request: AgentTaskRuntimeRequest,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class AgentTaskGraphState(TypedDict, total=False):
    program_id: str
    campaign_id: str | None
    correlation_id: str | None
    task_id: str
    message_id: str
    target_agent: str
    agent_key: str
    agent_route: str
    schema_version: str
    body_excerpt: str
    context: dict[str, Any]
    boundary: dict[str, Any]
    body: str
    message_kind: str
    status: str
    artifact_refs: list[dict[str, Any]]
    fact_refs: list[dict[str, Any]]
    graph_refs: list[dict[str, Any]]
    action_refs: list[dict[str, Any]]
    proposal_refs: list[dict[str, Any]]
    decision_refs: list[dict[str, Any]]
    proposal_drafts: list[dict[str, Any]]
    metadata: dict[str, Any]
    langgraph_thread_id: str
    langgraph_checkpoint_ns: str
