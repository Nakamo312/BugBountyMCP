"""Read-side activity stream for the agent workroom.

The activity stream gives the UI a lightweight way to poll for new visible
changes in the campaign cockpit: agent messages, proposals, proposal decisions,
and action queue status updates. It is deliberately a read model. It does not
execute agents, graph algorithms, or tools.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentActivityEventType(str, Enum):
    AGENT_MESSAGE = "agent_message"
    AGENT_PROPOSAL = "agent_proposal"
    PROPOSAL_DECISION = "proposal_decision"
    ACTION_STATUS = "action_status"


class AgentActivityEvent(BaseModel):
    """One visible workroom activity item for UI polling."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: AgentActivityEventType
    program_id: UUID
    campaign_id: UUID | None = None
    task_id: UUID | None = None
    occurred_at: datetime
    title: str
    summary: str
    actor: str | None = None
    status: str | None = None
    priority: str | None = None
    requires_attention: bool = False
    refs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentActivityStreamSnapshot(BaseModel):
    """Incremental activity stream payload for the campaign workroom UI."""

    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    campaign_id: UUID | None = None
    task_id: UUID | None = None
    generated_at: datetime
    after: datetime | None = None
    next_after: datetime | None = None
    events: list[AgentActivityEvent] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    boundaries: dict[str, Any] = Field(default_factory=dict)


class AgentActivityStore(Protocol):
    async def load_activity_stream(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_id: UUID | None = None,
        after: datetime | None = None,
        limit: int = 100,
    ) -> AgentActivityStreamSnapshot: ...


class AgentActivityService:
    """Read-side service for incremental UI activity.

    This service must remain a polling/read boundary. It does not call GDS,
    invoke LangGraph, enqueue inbox messages, or create ToolActionRequests.
    """

    def __init__(self, store: AgentActivityStore) -> None:
        self.store = store

    async def get_activity_stream(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_id: UUID | None = None,
        after: datetime | None = None,
        limit: int = 100,
    ) -> AgentActivityStreamSnapshot:
        return await self.store.load_activity_stream(
            program_id=program_id,
            campaign_id=campaign_id,
            task_id=task_id,
            after=after,
            limit=_bounded_limit(limit, default=100, maximum=500),
        )


def activity_boundaries() -> dict[str, Any]:
    return {
        "surface": "agent_activity_read_model",
        "polling": "timestamp_cursor",
        "agent_execution": "not_available_from_activity_api",
        "gds_execution": "not_available_from_activity_api",
        "tool_execution": "must_go_through_action_service",
        "proposal_execution": "requires_explicit_acceptance_then_policy_scope_approval_budget",
        "raw_artifact_access": "forbidden",
        "raw_response_body_access": "forbidden",
    }


def activity_counts(events: list[AgentActivityEvent]) -> dict[str, int]:
    return {
        "events": len(events),
        "agent_messages": sum(1 for event in events if event.event_type is AgentActivityEventType.AGENT_MESSAGE),
        "agent_proposals": sum(1 for event in events if event.event_type is AgentActivityEventType.AGENT_PROPOSAL),
        "proposal_decisions": sum(1 for event in events if event.event_type is AgentActivityEventType.PROPOSAL_DECISION),
        "action_status_updates": sum(1 for event in events if event.event_type is AgentActivityEventType.ACTION_STATUS),
        "requires_attention": sum(1 for event in events if event.requires_attention),
    }


def next_after_for(events: list[AgentActivityEvent]) -> datetime | None:
    if not events:
        return None
    return max(event.occurred_at for event in events)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _bounded_limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))
