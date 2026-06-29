"""Event-to-agent-inbox routing persistence."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from api.application.contracts import EventEnvelope
from api.infrastructure.adapters.orm import agent_subscriptions
from api.infrastructure.agent_inbox_store import AgentInboxMessage, AgentInboxStore


class AgentEventRouter:
    def __init__(self, session_factory, inbox_store: AgentInboxStore) -> None:
        self.session_factory = session_factory
        self.inbox_store = inbox_store

    async def route_event(self, event: EventEnvelope) -> int:
        campaign_id = self._optional_uuid(event.payload.get("campaign_id"))
        query = (
            select(
                agent_subscriptions.c.id,
                agent_subscriptions.c.workflow_id,
                agent_subscriptions.c.workflow_run_id,
                agent_subscriptions.c.program_id,
                agent_subscriptions.c.campaign_id,
                agent_subscriptions.c.correlation_id,
                agent_subscriptions.c.event_type,
            )
            .where(
                agent_subscriptions.c.program_id == event.program_id,
                agent_subscriptions.c.event_type == event.event,
                agent_subscriptions.c.status == "active",
                or_(
                    agent_subscriptions.c.campaign_id.is_(None),
                    agent_subscriptions.c.campaign_id == campaign_id,
                ),
                or_(
                    agent_subscriptions.c.correlation_id.is_(None),
                    agent_subscriptions.c.correlation_id == event.correlation_id,
                ),
            )
        )

        async with self.session_factory() as session:
            result = await session.execute(query)
            subscriptions = result.mappings().all()

        delivered = 0
        for subscription in subscriptions:
            await self.inbox_store.enqueue_once(
                AgentInboxMessage(
                    subscription_id=subscription["id"],
                    workflow_id=subscription["workflow_id"],
                    workflow_run_id=subscription["workflow_run_id"],
                    program_id=subscription["program_id"],
                    campaign_id=subscription["campaign_id"] or campaign_id,
                    correlation_id=subscription["correlation_id"] or event.correlation_id,
                    event_id=event.event_id,
                    message_type=event.event,
                    payload=event.model_dump(mode="json"),
                    dedupe_key=f"event:{event.event_id}:subscription:{subscription['id']}",
                )
            )
            delivered += 1

        return delivered

    @staticmethod
    def _optional_uuid(value: Any) -> UUID | None:
        if value is None or isinstance(value, UUID):
            return value
        return UUID(str(value))


__all__ = ["AgentEventRouter"]
