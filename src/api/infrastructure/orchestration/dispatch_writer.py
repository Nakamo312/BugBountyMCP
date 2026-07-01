"""Durable outbox writes for newly recorded domain events."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, insert, select

from api.application.contracts import EventEnvelope
from api.config import Settings
from api.infrastructure.adapters.orm import event_dispatches
from api.infrastructure.events.notify_channels import validate_postgres_notify_channel
from api.infrastructure.events.queue_config import QueueConfig


class DispatchWriterStore:
    """Append dispatch rows inside the caller's event-recording transaction."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    @staticmethod
    def notify_statement(*, channel: str, payload: str):
        return select(func.pg_notify(validate_postgres_notify_channel(channel), payload))

    async def enqueue_dispatch(
        self,
        session,
        envelope: EventEnvelope,
        *,
        destination: str = "rabbitmq",
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        await session.execute(
            insert(event_dispatches).values(
                id=uuid.uuid4(),
                event_id=envelope.event_id,
                destination=destination,
                routing_key=QueueConfig.get_routing_key(envelope.event),
                status="pending",
                attempts=0,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.execute(
            self.notify_statement(
                channel=self.settings.EVENT_DISPATCH_NOTIFY_CHANNEL,
                payload=str(envelope.event_id),
            )
        )
