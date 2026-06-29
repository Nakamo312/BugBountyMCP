"""Map LangGraph state into visible agent task runtime results."""
from __future__ import annotations

from typing import Any

from api.application.agent_action_proposals import AgentActionProposalDraft
from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest, AgentTaskRuntimeResult
from api.application.agent_task_langgraph_helpers import (
    agent_key,
    bounded_dicts,
    bounded_mapping,
    optional_text,
    optional_uuid_text,
)
from api.application.agent_task_langgraph_models import AgentTaskGraphState, AgentTaskLangGraphThreadRef
from api.application.agent_task_roles import AgentTaskRoleReply
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus


def graph_state_from_role_reply(
    state: AgentTaskGraphState,
    reply: AgentTaskRoleReply,
) -> AgentTaskGraphState:
    metadata = dict(state.get("metadata") or {})
    metadata.update(reply.metadata)
    metadata.setdefault("runtime", "langgraph-agent-task-runtime.v2")
    metadata.setdefault("graph", "agent-task-role-thread.v1")
    metadata["selected_agent_role"] = reply.agent_key
    return {
        "agent_key": reply.agent_key,
        "body": reply.body,
        "message_kind": reply.message_kind.value,
        "status": reply.status.value,
        "artifact_refs": list(reply.artifact_refs),
        "fact_refs": list(reply.fact_refs),
        "graph_refs": list(reply.graph_refs),
        "action_refs": list(reply.action_refs),
        "proposal_refs": list(reply.proposal_refs),
        "decision_refs": list(reply.decision_refs),
        "proposal_drafts": [draft.model_dump(mode="json") for draft in reply.proposal_drafts],
        "metadata": metadata,
    }


def input_state(
    request: AgentTaskRuntimeRequest,
    context: dict[str, Any],
) -> AgentTaskGraphState:
    return {
        "program_id": str(request.program_id),
        "campaign_id": optional_uuid_text(request.campaign_id),
        "correlation_id": optional_uuid_text(request.correlation_id),
        "task_id": str(request.task_id),
        "message_id": str(request.message_id),
        "target_agent": request.target_agent,
        "schema_version": request.schema_version,
        "body_excerpt": request.body_excerpt,
        "context": safe_context(context),
    }


def runtime_result_from_graph_state(
    *,
    request: AgentTaskRuntimeRequest,
    graph_state: dict[str, Any],
    context: dict[str, Any],
    thread_ref: AgentTaskLangGraphThreadRef | None = None,
) -> AgentTaskRuntimeResult:
    metadata = dict(graph_state.get("metadata") or {})
    boundary = dict(graph_state.get("boundary") or {})
    boundary.update(
        {
            "tool_execution": "forbidden_from_langgraph_agent_task_runtime",
            "raw_artifact_access": "forbidden",
            "next_step": "agent_may_reply_or_propose_bounded_action_request",
        }
    )
    metadata.update(
        {
            "runtime": metadata.get("runtime") or "langgraph-agent-task-runtime.v1",
            "source_message_id": str(request.message_id),
            "context_ref_count": len(context.get("context_refs") or []),
            "boundary": boundary,
        }
    )
    if thread_ref is not None:
        metadata.setdefault("langgraph_thread", thread_ref.to_metadata())
        metadata.setdefault("langgraph_thread_id", thread_ref.thread_id)
        metadata.setdefault("langgraph_checkpoint_ns", thread_ref.checkpoint_ns)
    return AgentTaskRuntimeResult(
        agent_key=agent_key(str(graph_state.get("agent_key") or request.target_agent)),
        body=reply_body(graph_state, request),
        message_kind=message_kind(graph_state.get("message_kind")),
        status=status(graph_state.get("status")),
        artifact_refs=tuple(bounded_dicts(graph_state.get("artifact_refs") or ())),
        fact_refs=tuple(bounded_dicts(graph_state.get("fact_refs") or ())),
        graph_refs=tuple(bounded_dicts(graph_state.get("graph_refs") or ())),
        action_refs=tuple(bounded_dicts(graph_state.get("action_refs") or ())),
        proposal_refs=tuple(bounded_dicts(graph_state.get("proposal_refs") or ())),
        decision_refs=tuple(bounded_dicts(graph_state.get("decision_refs") or ())),
        proposal_drafts=proposal_drafts(graph_state.get("proposal_drafts") or ()),
        metadata=metadata,
    )


def proposal_drafts(value: Any) -> tuple[AgentActionProposalDraft, ...]:
    drafts: list[AgentActionProposalDraft] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        try:
            drafts.append(AgentActionProposalDraft.model_validate(item))
        except Exception:
            continue
        if len(drafts) >= 10:
            break
    return tuple(drafts)


def reply_body(graph_state: dict[str, Any], request: AgentTaskRuntimeRequest) -> str:
    value = graph_state.get("body")
    if isinstance(value, str) and value.strip():
        return value.strip()[:8000]
    prompt = request.body_excerpt.strip() or "пустой промт"
    return (
        "Агент обработал задачу через LangGraph, но workflow не вернул текст. "
        "Инструменты не запускались из промта.\n\n"
        f"Кратко понял запрос: {prompt[:700]}"
    )


def message_kind(value: Any) -> AgentTaskMessageKind:
    try:
        return AgentTaskMessageKind(str(value))
    except Exception:
        return AgentTaskMessageKind.NOTE


def status(value: Any) -> AgentTaskStatus:
    try:
        return AgentTaskStatus(str(value))
    except Exception:
        return AgentTaskStatus.WAITING


def safe_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "program_id": optional_text(context.get("program_id")),
        "campaign_id": optional_text(context.get("campaign_id")),
        "correlation_id": optional_text(context.get("correlation_id")),
        "task_id": optional_text(context.get("task_id")),
        "message_id": optional_text(context.get("message_id")),
        "target_agent": optional_text(context.get("target_agent")),
        "context_refs": bounded_dicts(context.get("context_refs") or (), limit=25),
        "thread_messages": bounded_dicts(context.get("thread_messages") or (), limit=8),
        "recent_outcomes": bounded_dicts(context.get("recent_outcomes") or (), limit=8),
        "pending_proposals": bounded_dicts(context.get("pending_proposals") or (), limit=5),
        "surface_summary": bounded_mapping(context.get("surface_summary") or {}),
        "metadata_keys": [str(value)[:120] for value in context.get("metadata_keys") or []][:25],
        "langgraph_thread": bounded_mapping(context.get("langgraph_thread") or {}),
    }
