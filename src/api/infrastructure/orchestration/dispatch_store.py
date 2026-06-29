"""Scenario-owned persistence for outbox dispatch leasing and delivery state."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import EventDispatchRecord, EventEnvelope
from api.config import Settings
from api.infrastructure.adapters.orm import event_dispatches, event_store
from api.infrastructure.events.notify_channels import validate_postgres_notify_channel
from api.infrastructure.events.queue_config import QueueConfig


def event_envelope_from_event_store_row(row: Mapping[str, Any]) -> EventEnvelope:
    payload = dict(row.get("payload") or {})
    payload.update(
        {
            "event_id": row["event_id"],
            "event": row["event_type"],
            "program_id": row["program_id"],
            "correlation_id": row["correlation_id"],
            "causation_id": row.get("causation_id"),
            "source": row["source"],
            "profile": row.get("profile"),
            "confidence": row["confidence"],
            "created_at": row["event_created_at"],
        }
    )
    if row.get("job_id") is not None:
        payload["job_id"] = row["job_id"]
    if row.get("run_id") is not None:
        payload["run_id"] = row["run_id"]
    return EventEnvelope(**payload)


class DispatchStore:
    """Durable outbox write model for event dispatchers."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        settings: Settings | None = None,
    ):
        self.session_factory = session_factory
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

    async def claim_dispatches(
        self,
        *,
        destination: str,
        dispatcher_id: str,
        batch_size: int,
        lease_ttl_seconds: int,
    ) -> list[EventDispatchRecord]:
        now = datetime.now(timezone.utc)
        locked_until = now + timedelta(seconds=max(1, lease_ttl_seconds))

        async with self.session_factory() as session:
            rows = await self._select_claimable_dispatch_rows(
                session,
                destination=destination,
                now=now,
                limit=max(1, batch_size),
            )
            if not rows:
                await session.commit()
                return []

            await self._mark_dispatch_rows_locked(
                session,
                rows=rows,
                dispatcher_id=dispatcher_id,
                locked_until=locked_until,
                now=now,
            )
            await session.commit()

        return [self._dispatch_record_from_row(row) for row in rows]

    @staticmethod
    def _claimable_dispatch_predicates(*, now: datetime):
        pending_or_failed = (
            event_dispatches.c.status.in_(["pending", "failed"])
            & (event_dispatches.c.available_at <= now)
        )
        expired_lock = (
            (event_dispatches.c.status == "locked")
            & (event_dispatches.c.locked_until.is_not(None))
            & (event_dispatches.c.locked_until <= now)
        )
        return pending_or_failed, expired_lock

    async def _select_claimable_dispatch_rows(
        self,
        session,
        *,
        destination: str,
        now: datetime,
        limit: int,
    ):
        pending_or_failed, expired_lock = self._claimable_dispatch_predicates(now=now)
        result = await session.execute(
            select(
                event_dispatches.c.id.label("dispatch_id"),
                event_dispatches.c.event_id,
                event_dispatches.c.destination,
                event_dispatches.c.routing_key,
                event_dispatches.c.attempts,
                event_store.c.event_type,
                event_store.c.program_id,
                event_store.c.job_id,
                event_store.c.run_id,
                event_store.c.correlation_id,
                event_store.c.causation_id,
                event_store.c.source,
                event_store.c.profile,
                event_store.c.confidence,
                event_store.c.payload,
                event_store.c.created_at.label("event_created_at"),
            )
            .select_from(
                event_dispatches.join(
                    event_store,
                    event_dispatches.c.event_id == event_store.c.event_id,
                )
            )
            .where(
                event_dispatches.c.destination == destination,
                or_(pending_or_failed, expired_lock),
            )
            .order_by(
                event_dispatches.c.available_at.asc(),
                event_dispatches.c.created_at.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True, of=event_dispatches)
        )
        return result.mappings().all()

    @staticmethod
    async def _mark_dispatch_rows_locked(
        session,
        *,
        rows,
        dispatcher_id: str,
        locked_until: datetime,
        now: datetime,
    ) -> None:
        await session.execute(
            update(event_dispatches)
            .where(event_dispatches.c.id.in_([row["dispatch_id"] for row in rows]))
            .values(
                status="locked",
                locked_by=dispatcher_id,
                locked_until=locked_until,
                updated_at=now,
            )
        )

    @staticmethod
    def _dispatch_record_from_row(row) -> EventDispatchRecord:
        return EventDispatchRecord(
            dispatch_id=row["dispatch_id"],
            event_id=row["event_id"],
            destination=row["destination"],
            routing_key=row["routing_key"],
            attempts=int(row["attempts"] or 0),
            envelope=event_envelope_from_event_store_row(row),
        )

    async def mark_sent(
        self,
        *,
        dispatch_id: uuid.UUID,
        dispatcher_id: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                update(event_dispatches)
                .where(
                    event_dispatches.c.id == dispatch_id,
                    event_dispatches.c.locked_by == dispatcher_id,
                )
                .values(
                    status="dispatched",
                    dispatched_at=now,
                    locked_by=None,
                    locked_until=None,
                    updated_at=now,
                )
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def mark_failed(
        self,
        *,
        dispatch_id: uuid.UUID,
        dispatcher_id: str,
        error: str,
        current_attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> bool:
        now = datetime.now(timezone.utc)
        next_attempts = max(0, int(current_attempts)) + 1
        status = "dead" if next_attempts >= max(1, int(max_attempts)) else "failed"
        available_at = (
            now if status == "dead" else now + timedelta(seconds=max(0.1, retry_delay_seconds))
        )
        async with self.session_factory() as session:
            result = await session.execute(
                update(event_dispatches)
                .where(
                    event_dispatches.c.id == dispatch_id,
                    event_dispatches.c.locked_by == dispatcher_id,
                )
                .values(
                    status=status,
                    attempts=next_attempts,
                    available_at=available_at,
                    locked_by=None,
                    locked_until=None,
                    last_error=error[:4000],
                    updated_at=now,
                )
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1
