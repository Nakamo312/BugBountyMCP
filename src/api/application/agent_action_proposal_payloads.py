"""Payload/key helpers for agent action proposals."""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID, uuid4

from api.application.research.sanitizer import sanitize_json, sanitize_text

from .agent_action_proposal_models import (
    AGENT_ACTION_PROPOSAL_MAX_CHARS,
    AGENT_ACTION_PROPOSAL_SCHEMA_VERSION,
    AgentActionProposalAcceptRequest,
    AgentActionProposalDraft,
    AgentActionProposalRecord,
    AgentActionProposalWrite,
)


def proposal_write_from_draft(
    *,
    program_id: UUID,
    campaign_id: UUID | None,
    task_id: UUID,
    source_message_id: UUID,
    agent_key: str,
    draft: AgentActionProposalDraft,
    index: int,
) -> AgentActionProposalWrite:
    title = sanitize_text(draft.title, limit=200).safe_excerpt[:200]
    summary = sanitize_text(draft.summary, limit=AGENT_ACTION_PROPOSAL_MAX_CHARS).safe_excerpt
    rationale = sanitize_text(draft.rationale or "", limit=AGENT_ACTION_PROPOSAL_MAX_CHARS).safe_excerpt
    context_refs = sanitize_json(draft.context_refs)
    metadata = proposal_metadata(draft.metadata)
    proposal_key = _proposal_key(
        task_id=task_id,
        source_message_id=source_message_id,
        agent_key=agent_key,
        title=title,
        summary=summary,
        index=index,
    )
    normalized_draft = draft.model_copy(
        update={
            "title": title or "Agent proposal",
            "summary": summary or "Агент предложил следующий шаг, но текст был пуст после санитарной обработки.",
            "rationale": rationale,
            "context_refs": context_refs,
            "metadata": metadata,
            "action_params": sanitize_json(draft.action_params),
        }
    )
    return AgentActionProposalWrite(
        proposal_id=uuid4(),
        program_id=program_id,
        campaign_id=campaign_id,
        task_id=task_id,
        source_message_id=source_message_id,
        agent_key=_agent_key(agent_key),
        proposal_key=proposal_key,
        draft=normalized_draft,
        title=normalized_draft.title,
        summary=normalized_draft.summary,
        rationale=normalized_draft.rationale or "",
        context_refs=context_refs,
        metadata=metadata,
    )


def proposal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return sanitize_json(
        {
            **metadata,
            "schema_version": AGENT_ACTION_PROPOSAL_SCHEMA_VERSION,
            "source": "agent_task_runtime",
            "proposal_boundary": {
                "tool_execution": "forbidden_from_agent_proposal",
                "next_step": "operator_or_scheduler_must_create_action_request",
                "action_service_required": True,
            },
        }
    )


def proposal_record_ref(record: AgentActionProposalRecord) -> dict[str, Any]:
    """Compact reference stored on a visible agent task message."""

    return {
        "kind": "agent_action_proposal",
        "proposal_id": str(record.proposal_id),
        "task_id": str(record.task_id),
        "agent_key": record.agent_key,
        "proposal_type": record.proposal_type.value,
        "status": record.status.value,
        "title": record.title,
        "capability_id": record.capability_id,
        "profile_id": record.profile_id,
        "priority": record.priority,
        "risk_level": record.risk_level,
        "accepted_action_id": str(record.accepted_action_id) if record.accepted_action_id else None,
        "reviewed_at": record.reviewed_at.isoformat() if hasattr(record.reviewed_at, "isoformat") else record.reviewed_at,
        "approval": "required_via_action_service",
    }


def _proposal_key(
    *,
    task_id: UUID,
    source_message_id: UUID,
    agent_key: str,
    title: str,
    summary: str,
    index: int,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            [
                str(task_id),
                str(source_message_id),
                _agent_key(agent_key),
                str(index),
                title.strip().lower(),
                summary.strip().lower(),
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"agent-task:{task_id}:{source_message_id}:{index}:{digest[:16]}"


def _agent_key(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    return normalized[:100] or "agent"


def targets_from_accept_request(
    request: AgentActionProposalAcceptRequest,
    proposal: AgentActionProposalRecord,
) -> list[str]:
    if request.targets:
        return list(request.targets)
    raw_targets = proposal.action_params.get("targets")
    if raw_targets is None and "target" in proposal.action_params:
        raw_targets = [proposal.action_params["target"]]
    if raw_targets is None:
        return []
    candidates = [raw_targets] if isinstance(raw_targets, str) else list(raw_targets)
    return [str(target).strip() for target in candidates if str(target).strip()]


def options_from_accept_request(
    request: AgentActionProposalAcceptRequest,
    proposal: AgentActionProposalRecord,
) -> dict[str, Any]:
    base = proposal.action_params.get("options")
    options = dict(base) if isinstance(base, dict) else {}
    options.update(sanitize_json(request.options))
    return options
