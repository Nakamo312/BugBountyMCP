"""Postgres read store for the agent workroom activity stream."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select

from api.application.agent_activity import (
    AgentActivityEvent,
    AgentActivityEventType,
    AgentActivityStreamSnapshot,
    activity_boundaries,
    activity_counts,
    next_after_for,
    now_utc,
)
from api.infrastructure.adapters.orm import (
    action_requests,
    agent_action_proposal_feedback_events,
    agent_action_proposals,
    agent_task_messages,
)


class AgentActivityStore:
    """Build an incremental activity payload from durable state.

    This store is intentionally read-only. It does not trigger agent processing,
    graph algorithms, proposal generation, or tool execution.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def load_activity_stream(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_id: UUID | None = None,
        after: datetime | None = None,
        limit: int = 100,
    ) -> AgentActivityStreamSnapshot:
        per_source_limit = max(1, limit)
        async with self.session_factory() as session:
            message_rows = await self._load_message_events(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                task_id=task_id,
                after=after,
                limit=per_source_limit,
            )
            proposal_rows = await self._load_proposal_events(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                task_id=task_id,
                after=after,
                limit=per_source_limit,
            )
            feedback_rows = await self._load_feedback_events(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                task_id=task_id,
                after=after,
                limit=per_source_limit,
            )
            action_rows = await self._load_action_events(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                task_id=task_id,
                after=after,
                limit=per_source_limit,
            )

        events = [
            *(_message_event(row) for row in message_rows),
            *(_proposal_event(row) for row in proposal_rows),
            *(_feedback_event(row) for row in feedback_rows),
            *(_action_event(row) for row in action_rows),
        ]
        events = sorted(events, key=lambda event: (event.occurred_at, event.event_id), reverse=True)[:limit]
        events = list(reversed(events))
        return AgentActivityStreamSnapshot(
            program_id=program_id,
            campaign_id=campaign_id,
            task_id=task_id,
            generated_at=now_utc(),
            after=after,
            next_after=next_after_for(events),
            events=events,
            counts=activity_counts(events),
            boundaries=activity_boundaries(),
        )

    async def _load_message_events(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID | None,
        after: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(agent_task_messages).where(agent_task_messages.c.program_id == program_id)
        if campaign_id is not None:
            statement = statement.where(agent_task_messages.c.campaign_id == campaign_id)
        if task_id is not None:
            statement = statement.where(agent_task_messages.c.task_id == task_id)
        if after is not None:
            statement = statement.where(agent_task_messages.c.created_at > after)
        statement = statement.order_by(desc(agent_task_messages.c.created_at), desc(agent_task_messages.c.id)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_proposal_events(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID | None,
        after: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(agent_action_proposals).where(agent_action_proposals.c.program_id == program_id)
        if campaign_id is not None:
            statement = statement.where(agent_action_proposals.c.campaign_id == campaign_id)
        if task_id is not None:
            statement = statement.where(agent_action_proposals.c.task_id == task_id)
        if after is not None:
            statement = statement.where(
                or_(
                    agent_action_proposals.c.created_at > after,
                    agent_action_proposals.c.updated_at > after,
                    agent_action_proposals.c.accepted_at > after,
                    agent_action_proposals.c.reviewed_at > after,
                )
            )
        statement = statement.order_by(desc(agent_action_proposals.c.updated_at), desc(agent_action_proposals.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_feedback_events(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID | None,
        after: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(agent_action_proposal_feedback_events).where(
            agent_action_proposal_feedback_events.c.program_id == program_id
        )
        if campaign_id is not None:
            statement = statement.where(agent_action_proposal_feedback_events.c.campaign_id == campaign_id)
        if task_id is not None:
            statement = statement.where(agent_action_proposal_feedback_events.c.task_id == task_id)
        if after is not None:
            statement = statement.where(agent_action_proposal_feedback_events.c.created_at > after)
        statement = statement.order_by(desc(agent_action_proposal_feedback_events.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_action_events(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_id: UUID | None,
        after: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if task_id is not None:
            statement = (
                select(action_requests)
                .select_from(
                    action_requests.join(
                        agent_action_proposals,
                        action_requests.c.id == agent_action_proposals.c.accepted_action_id,
                    )
                )
                .where(agent_action_proposals.c.task_id == task_id)
                .where(action_requests.c.program_id == program_id)
            )
        else:
            statement = select(action_requests).where(action_requests.c.program_id == program_id)
        if campaign_id is not None:
            statement = statement.where(action_requests.c.campaign_id == campaign_id)
        if after is not None:
            statement = statement.where(or_(action_requests.c.created_at > after, action_requests.c.updated_at > after))
        statement = statement.order_by(desc(action_requests.c.updated_at), desc(action_requests.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]


def _message_event(row: dict[str, Any]) -> AgentActivityEvent:
    role = row.get("role") or "message"
    message_kind = row.get("message_kind") or "note"
    agent_key = row.get("agent_key")
    title = _message_title(role=role, message_kind=message_kind, agent_key=agent_key)
    return AgentActivityEvent(
        event_id=f"agent-message:{row['id']}",
        event_type=AgentActivityEventType.AGENT_MESSAGE,
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        task_id=row.get("task_id"),
        occurred_at=row["created_at"],
        title=title,
        summary=_safe_text(row.get("body"), limit=420),
        actor=agent_key or role,
        status=message_kind,
        requires_attention=message_kind in {"question", "decision", "error"},
        refs={
            "message_id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "artifact_refs": row.get("artifact_refs") or [],
            "fact_refs": row.get("fact_refs") or [],
            "graph_refs": row.get("graph_refs") or [],
            "action_refs": row.get("action_refs") or [],
            "proposal_refs": row.get("proposal_refs") or [],
            "decision_refs": row.get("decision_refs") or [],
        },
        metadata={
            "role": role,
            "message_kind": message_kind,
            "boundary": "visible_agent_task_thread",
        },
    )


def _proposal_event(row: dict[str, Any]) -> AgentActivityEvent:
    status = row.get("status") or "pending"
    occurred_at = _proposal_event_time(row)
    return AgentActivityEvent(
        event_id=f"agent-proposal:{row['id']}:{status}",
        event_type=AgentActivityEventType.AGENT_PROPOSAL,
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        task_id=row.get("task_id"),
        occurred_at=occurred_at,
        title=f"Proposal: {_safe_text(row.get('title'), limit=140)}",
        summary=_safe_text(row.get("summary"), limit=420),
        actor=row.get("agent_key"),
        status=status,
        priority=row.get("priority"),
        requires_attention=status == "pending",
        refs={
            "proposal_id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "source_message_id": str(row["source_message_id"]),
            "accepted_action_id": str(row["accepted_action_id"]) if row.get("accepted_action_id") else None,
        },
        metadata={
            "proposal_type": row.get("proposal_type"),
            "risk_level": row.get("risk_level"),
            "expected_gain_excerpt": _safe_text(row.get("expected_gain"), limit=240),
            "action_intent_excerpt": _safe_text(row.get("action_intent"), limit=240),
            "boundary": "advisory_proposal_not_execution",
        },
    )


def _feedback_event(row: dict[str, Any]) -> AgentActivityEvent:
    feedback_type = row.get("feedback_type") or row.get("new_status") or "reviewed"
    return AgentActivityEvent(
        event_id=f"proposal-feedback:{row['id']}",
        event_type=AgentActivityEventType.PROPOSAL_DECISION,
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        task_id=row.get("task_id"),
        occurred_at=row["created_at"],
        title=f"Proposal {feedback_type}",
        summary=_safe_text(row.get("reason"), limit=420) or f"Proposal was {feedback_type}.",
        actor=row.get("actor"),
        status=feedback_type,
        requires_attention=False,
        refs={
            "feedback_event_id": str(row["id"]),
            "proposal_id": str(row["proposal_id"]),
            "task_id": str(row["task_id"]),
            "source_message_id": str(row["source_message_id"]),
        },
        metadata={
            "previous_status": row.get("previous_status"),
            "new_status": row.get("new_status"),
            "confidence": row.get("confidence"),
            "feedback_tags": row.get("feedback_tags") or [],
            "boundary": "human_feedback_signal",
        },
    )


def _action_event(row: dict[str, Any]) -> AgentActivityEvent:
    status = row.get("status") or "unknown"
    return AgentActivityEvent(
        event_id=f"action-status:{row['id']}:{status}",
        event_type=AgentActivityEventType.ACTION_STATUS,
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        task_id=_task_id_from_action_metadata(row.get("metadata") or {}),
        occurred_at=row.get("updated_at") or row["created_at"],
        title=f"Action {status}",
        summary=f"{row.get('capability_id')} / {row.get('profile_id')}",
        actor=row.get("requested_by"),
        status=status,
        requires_attention=status in {"requires_approval", "blocked", "rejected"},
        refs={
            "action_id": str(row["id"]),
            "campaign_id": str(row["campaign_id"]) if row.get("campaign_id") else None,
        },
        metadata={
            "kind": row.get("kind"),
            "capability_id": row.get("capability_id"),
            "profile_id": row.get("profile_id"),
            "boundary": "action_service_state",
        },
    )


def _message_title(*, role: str, message_kind: str, agent_key: str | None) -> str:
    if role == "user":
        return "Human prompt"
    if role == "system":
        return "System event"
    if agent_key:
        return f"{agent_key} · {message_kind}"
    return f"Agent · {message_kind}"


def _proposal_event_time(row: dict[str, Any]) -> datetime:
    if row.get("accepted_at") is not None:
        return row["accepted_at"]
    if row.get("reviewed_at") is not None:
        return row["reviewed_at"]
    return row.get("updated_at") or row["created_at"]


def _task_id_from_action_metadata(metadata: dict[str, Any]) -> UUID | None:
    value = metadata.get("agent_task_id") or metadata.get("task_id")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any, *, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"
