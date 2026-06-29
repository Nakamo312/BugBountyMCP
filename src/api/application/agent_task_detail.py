"""User-facing detail read model for one agent task.

The task detail screen is the working area where a human reads the live agent
thread, reviews proposals, sees accepted actions, and gets compact related
context. It is a read-side boundary: no agents, graph algorithms, raw artifacts,
or tools are executed from this service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.application.agent_action_proposals import AgentActionProposalRecord
from api.application.agent_tasks import AgentTaskMessageRecord, AgentTaskRecord
from api.application.agent_runtime_usage import AgentRuntimeUsageSummary
from api.application.campaign_workspace import CampaignWorkspaceActionQueueItem


class AgentTaskDetailOutcomeItem(BaseModel):
    """Compact outcome memory item related to the task context."""

    model_config = ConfigDict(extra="forbid")

    outcome_id: UUID
    program_id: UUID
    campaign_id: UUID | None = None
    action_id: UUID
    run_id: UUID
    capability_id: str
    profile_id: str
    node_id: str | None = None
    event_name: str | None = None
    status: str
    terminal_outcome: str | None = None
    information_gain_score: float
    counts: dict[str, int] = Field(default_factory=dict)
    human_feedback: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentTaskDetailContext(BaseModel):
    """Compact context for the task detail screen.

    This is intentionally smaller than an evidence/artifact view. It gives the UI
    enough state to explain what the agent is seeing without exposing raw logs or
    creating another execution path.
    """

    model_config = ConfigDict(extra="forbid")

    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    thread_summary: dict[str, int] = Field(default_factory=dict)
    proposal_summary: dict[str, int] = Field(default_factory=dict)
    action_summary: dict[str, int] = Field(default_factory=dict)
    outcome_summary: dict[str, Any] = Field(default_factory=dict)
    agent_runtime_usage: AgentRuntimeUsageSummary = Field(default_factory=AgentRuntimeUsageSummary)
    surface_summary: dict[str, Any] = Field(default_factory=dict)
    last_user_message_excerpt: str | None = None
    last_agent_message_excerpt: str | None = None
    boundaries: dict[str, Any] = Field(default_factory=dict)


class AgentTaskDetailSnapshot(BaseModel):
    """Single payload for the concrete agent task UI screen."""

    model_config = ConfigDict(extra="forbid")

    task: AgentTaskRecord
    messages: list[AgentTaskMessageRecord] = Field(default_factory=list)
    proposals: list[AgentActionProposalRecord] = Field(default_factory=list)
    decisions: list[AgentTaskMessageRecord] = Field(default_factory=list)
    accepted_actions: list[CampaignWorkspaceActionQueueItem] = Field(default_factory=list)
    related_outcomes: list[AgentTaskDetailOutcomeItem] = Field(default_factory=list)
    compact_context: AgentTaskDetailContext
    counts: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime


class AgentTaskDetailStore(Protocol):
    async def load_task_detail(
        self,
        *,
        task_id: UUID,
        message_limit: int = 100,
        proposal_limit: int = 50,
        outcome_limit: int = 20,
        surface_sample_limit: int = 8,
    ) -> AgentTaskDetailSnapshot | None: ...


class AgentTaskDetailService:
    """Read-side service for the task detail screen.

    It does not run agents, GDS, or tools. It only assembles already-durable state
    for the UI.
    """

    def __init__(self, store: AgentTaskDetailStore) -> None:
        self.store = store

    async def get_task_detail(
        self,
        *,
        task_id: UUID,
        message_limit: int = 100,
        proposal_limit: int = 50,
        outcome_limit: int = 20,
        surface_sample_limit: int = 8,
    ) -> AgentTaskDetailSnapshot | None:
        return await self.store.load_task_detail(
            task_id=task_id,
            message_limit=_bounded_limit(message_limit, default=100, maximum=500),
            proposal_limit=_bounded_limit(proposal_limit, default=50, maximum=200),
            outcome_limit=_bounded_limit(outcome_limit, default=20, maximum=100),
            surface_sample_limit=_bounded_limit(surface_sample_limit, default=8, maximum=50),
        )


def task_detail_boundaries() -> dict[str, Any]:
    return {
        "surface": "agent_task_detail_read_model",
        "agent_execution": "not_available_from_task_detail_api",
        "gds_execution": "not_available_from_task_detail_api",
        "tool_execution": "must_go_through_action_service",
        "proposal_execution": "requires_explicit_acceptance_then_policy_scope_approval_budget",
        "raw_artifact_access": "forbidden",
        "raw_response_body_access": "forbidden",
    }


def task_detail_counts(snapshot: AgentTaskDetailSnapshot) -> dict[str, int]:
    return {
        "messages": len(snapshot.messages),
        "proposals": len(snapshot.proposals),
        "pending_proposals": sum(1 for proposal in snapshot.proposals if proposal.status.value == "pending"),
        "decisions": len(snapshot.decisions),
        "accepted_actions": len(snapshot.accepted_actions),
        "related_outcomes": len(snapshot.related_outcomes),
        "agent_runtime_decisions": snapshot.compact_context.agent_runtime_usage.runtime_decision_messages,
        "agent_runtime_llm_allowed": snapshot.compact_context.agent_runtime_usage.llm_allowed_messages,
        "agent_runtime_deep_downgraded": snapshot.compact_context.agent_runtime_usage.deep_downgraded_messages,
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))
