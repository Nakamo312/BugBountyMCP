"""User-facing campaign workspace read model.

This module assembles the agent workroom UI state without exposing internal
Neo4j/GDS execution details. It is a read-side boundary for the product cockpit:
agent tasks, visible thread messages, proposals, decisions, and current action
queue. It does not run graph algorithms, agents, or tools.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.application.agent_action_proposals import AgentActionProposalRecord
from api.application.agent_tasks import AgentTaskMessageRecord, AgentTaskRecord
from api.application.agent_runtime_usage import AgentRuntimeUsageSummary


class CampaignWorkspaceActionStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    QUEUED = "queued"
    REJECTED = "rejected"


class CampaignWorkspaceActionQueueItem(BaseModel):
    """Compact action queue item for the campaign workroom."""

    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    status: CampaignWorkspaceActionStatus
    capability_id: str
    profile_id: str
    requested_by: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CampaignWorkspaceExperienceProposalItem(BaseModel):
    """Compact internal experience proposal for UI review.

    These proposals come from outcome-memory/Neo4j/GDS workers. The UI may show
    them, but recomputation and GDS remain internal worker concerns.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    proposal_run_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    status: str
    rank: int
    capability_id: str
    profile_id: str
    utility_score: float
    sample_count: int
    avg_similarity: float
    explanation: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CampaignWorkspaceTaskCard(BaseModel):
    """One visible task with recent thread and proposals."""

    model_config = ConfigDict(extra="forbid")

    task: AgentTaskRecord
    messages: list[AgentTaskMessageRecord] = Field(default_factory=list)
    proposals: list[AgentActionProposalRecord] = Field(default_factory=list)
    decisions: list[AgentTaskMessageRecord] = Field(default_factory=list)


class CampaignWorkspaceSnapshot(BaseModel):
    """Single payload for the campaign workroom UI."""

    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    campaign_id: UUID | None = None
    generated_at: datetime
    tasks: list[CampaignWorkspaceTaskCard] = Field(default_factory=list)
    pending_agent_proposals: list[AgentActionProposalRecord] = Field(default_factory=list)
    pending_experience_proposals: list[CampaignWorkspaceExperienceProposalItem] = Field(default_factory=list)
    recent_decisions: list[AgentTaskMessageRecord] = Field(default_factory=list)
    action_queue: list[CampaignWorkspaceActionQueueItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    agent_runtime_usage: AgentRuntimeUsageSummary = Field(default_factory=AgentRuntimeUsageSummary)
    boundaries: dict[str, Any] = Field(default_factory=dict)


class CampaignWorkspaceStore(Protocol):
    async def load_workspace(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_limit: int = 20,
        message_limit_per_task: int = 8,
        proposal_limit: int = 20,
        action_limit: int = 20,
    ) -> CampaignWorkspaceSnapshot: ...


class CampaignWorkspaceService:
    """Read-side service for the simplified campaign workroom.

    The service does not execute actions, run agents, or trigger GDS. It only
    returns already-durable state that the UI can render as a cockpit.
    """

    def __init__(self, store: CampaignWorkspaceStore) -> None:
        self.store = store

    async def get_workspace(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_limit: int = 20,
        message_limit_per_task: int = 8,
        proposal_limit: int = 20,
        action_limit: int = 20,
    ) -> CampaignWorkspaceSnapshot:
        return await self.store.load_workspace(
            program_id=program_id,
            campaign_id=campaign_id,
            task_limit=_bounded_limit(task_limit, default=20, maximum=100),
            message_limit_per_task=_bounded_limit(message_limit_per_task, default=8, maximum=50),
            proposal_limit=_bounded_limit(proposal_limit, default=20, maximum=100),
            action_limit=_bounded_limit(action_limit, default=20, maximum=100),
        )


def workspace_boundaries() -> dict[str, Any]:
    return {
        "surface": "ui_read_model",
        "gds_execution": "not_available_from_workspace_api",
        "agent_execution": "not_available_from_workspace_api",
        "tool_execution": "must_go_through_action_service",
        "proposal_execution": "requires_explicit_acceptance_then_policy_scope_approval_budget",
        "raw_artifact_access": "forbidden",
    }


def workspace_counts(snapshot: CampaignWorkspaceSnapshot) -> dict[str, int]:
    return {
        "tasks": len(snapshot.tasks),
        "visible_messages": sum(len(task.messages) for task in snapshot.tasks),
        "pending_agent_proposals": len(snapshot.pending_agent_proposals),
        "pending_experience_proposals": len(snapshot.pending_experience_proposals),
        "recent_decisions": len(snapshot.recent_decisions),
        "action_queue": len(snapshot.action_queue),
        "agent_runtime_decisions": snapshot.agent_runtime_usage.runtime_decision_messages,
        "agent_runtime_llm_allowed": snapshot.agent_runtime_usage.llm_allowed_messages,
        "agent_runtime_deep_downgraded": snapshot.agent_runtime_usage.deep_downgraded_messages,
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))
