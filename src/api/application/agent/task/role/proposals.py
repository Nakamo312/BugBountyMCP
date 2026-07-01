"""Proposal draft helpers for agent task role nodes."""
from __future__ import annotations

from typing import Any

from api.application.agent_action_proposals import (
    AgentActionProposalDraft,
    AgentActionProposalType,
)
from api.application.agent.task.role.context import (
    ContextRefSummary,
    _dedupe_ref_tuple,
    _safe_ref,
)


def _role_metadata(role: str, summary: ContextRefSummary) -> dict[str, Any]:
    return {
        "role_node": f"{role}.v2",
        "agent_role": role,
        "context_summary": summary.as_metadata(),
        "tool_execution": "forbidden_from_role_node",
        "raw_artifact_access": "forbidden",
    }


def _proposal_draft(
    *,
    title: str,
    summary: str,
    rationale: str,
    priority: str = "medium",
    risk_level: str = "low",
    expected_gain: str = "",
    action_intent: str = "",
    context_refs: tuple[dict[str, Any], ...] = tuple(),
) -> AgentActionProposalDraft:
    return AgentActionProposalDraft(
        proposal_type=AgentActionProposalType.INVESTIGATION_TASK,
        title=title,
        summary=summary,
        rationale=rationale,
        priority=priority,
        risk_level=risk_level,
        expected_gain=expected_gain,
        action_intent=action_intent,
        context_refs=list(context_refs),
        metadata={
            "proposal_origin": "agent_role_node",
            "tool_execution": "forbidden_from_role_node",
            "action_service_required": True,
        },
    )


def _proposal_context_refs(summary: ContextRefSummary) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    for kind in ("surface", "graph", "artifact", "fact", "decision", "context", "evidence"):
        refs.extend(summary.refs_by_kind.get(kind, ())[:3])
    for item in summary.recent_http[:2]:
        refs.append({
            "kind": "http_observation",
            "id": item.get("observation_id"),
            "url": item.get("url_excerpt"),
            "status_code": item.get("status_code"),
        })
    for item in summary.recent_javascript[:2]:
        refs.append({
            "kind": "javascript_reference",
            "id": item.get("reference_id"),
            "referenced_url": item.get("referenced_url_excerpt"),
        })
    return tuple(_dedupe_ref_tuple(refs, limit=10))
