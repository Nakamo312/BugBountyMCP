"""Models for deterministic agent task role replies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.application.agent_action_proposals import AgentActionProposalDraft
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus


@dataclass(frozen=True, slots=True)
class AgentTaskRoleReply:
    """Typed response produced by a role-specific agent node."""

    agent_key: str
    body: str
    message_kind: AgentTaskMessageKind
    status: AgentTaskStatus = AgentTaskStatus.WAITING
    artifact_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    fact_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    graph_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    action_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    proposal_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    decision_refs: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    proposal_drafts: tuple[AgentActionProposalDraft, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
