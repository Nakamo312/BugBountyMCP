"""Claim statement helpers for agent protocol inbox messages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update

from api.infrastructure.adapters.orm import agent_inbox, agent_subscriptions


@dataclass(frozen=True, slots=True)
class AgentInboxClaimRequest:
    program_id: Any | None
    consumer_id: str
    lease_seconds: int
    campaign_id: Any | None
    correlation_id: Any | None
    inbox_key: str | None
    message_type: str | None
    limit: int
    now: datetime

    @property
    def bounded_limit(self) -> int:
        return max(1, min(self.limit, 500))

    @property
    def lease_deadline(self) -> datetime:
        return self.now + timedelta(seconds=self.lease_seconds)


def claim_request(
    *,
    program_id: Any | None,
    consumer_id: str,
    lease_seconds: int,
    campaign_id: Any | None,
    correlation_id: Any | None,
    inbox_key: str | None,
    message_type: str | None,
    limit: int,
    now: datetime | None,
) -> AgentInboxClaimRequest:
    if not consumer_id.strip():
        raise ValueError("consumer_id must not be empty")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    if inbox_key is not None and not inbox_key.strip():
        raise ValueError("inbox_key must not be empty")
    if message_type is not None and not message_type.strip():
        raise ValueError("message_type must not be empty")
    return AgentInboxClaimRequest(
        program_id=program_id,
        consumer_id=consumer_id,
        lease_seconds=lease_seconds,
        campaign_id=campaign_id,
        correlation_id=correlation_id,
        inbox_key=inbox_key,
        message_type=message_type,
        limit=limit,
        now=now or datetime.now(timezone.utc),
    )


def claim_inbox_statement(request: AgentInboxClaimRequest):
    claimable = (
        _claimable_inbox_query(request)
        .order_by(agent_inbox.c.available_at.asc(), agent_inbox.c.created_at.asc())
        .limit(request.bounded_limit)
        .with_for_update(skip_locked=True)
        .cte("claimable_agent_inbox")
    )
    return (
        update(agent_inbox)
        .where(agent_inbox.c.id.in_(select(claimable.c.id)))
        .values(
            status="claimed",
            locked_by=request.consumer_id,
            locked_until=request.lease_deadline,
            attempts=agent_inbox.c.attempts + 1,
            updated_at=request.now,
            last_error=None,
        )
        .returning(agent_inbox)
    )


def _claimable_inbox_query(request: AgentInboxClaimRequest):
    query = select(agent_inbox.c.id).select_from(agent_inbox).where(
        agent_inbox.c.available_at <= request.now,
        or_(
            agent_inbox.c.status.in_(["pending", "failed"]),
            (
                (agent_inbox.c.status == "claimed")
                & (agent_inbox.c.locked_until.is_not(None))
                & (agent_inbox.c.locked_until <= request.now)
            ),
        ),
    )
    if request.program_id is not None:
        query = query.where(agent_inbox.c.program_id == request.program_id)
    if request.inbox_key is not None:
        query = query.join(
            agent_subscriptions,
            agent_subscriptions.c.id == agent_inbox.c.subscription_id,
        ).where(agent_subscriptions.c.inbox_key == request.inbox_key)
    if request.message_type is not None:
        query = query.where(agent_inbox.c.message_type == request.message_type)
    if request.campaign_id is not None:
        query = query.where(agent_inbox.c.campaign_id == request.campaign_id)
    if request.correlation_id is not None:
        query = query.where(agent_inbox.c.correlation_id == request.correlation_id)
    return query


__all__ = ["claim_inbox_statement", "claim_request"]
