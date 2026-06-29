"""Scenario-owned persistence for durable orchestration events."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import EventEnvelope, ExecutionStatus
from api.infrastructure.adapters.orm import event_store, runs


def event_store_payload(envelope: EventEnvelope) -> dict[str, Any]:
    payload = envelope.to_legacy_dict()
    payload.pop("event_id", None)
    payload.pop("created_at", None)
    return payload


async def insert_event_store_row(session, envelope: EventEnvelope) -> None:
    await session.execute(
        insert(event_store).values(
            id=uuid.uuid4(),
            event_id=envelope.event_id,
            event_type=envelope.event,
            program_id=envelope.program_id,
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            source=envelope.source,
            profile=envelope.profile,
            confidence=envelope.confidence,
            payload=event_store_payload(envelope),
            created_at=envelope.created_at,
        )
    )


def is_duplicate_event_integrity_error(exc: IntegrityError) -> bool:
    """Return true only for the event_store.event_id uniqueness violation.

    The event recorder is idempotent for duplicate event ids. Other integrity
    failures, such as foreign-key or not-null violations, must escape.
    """
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name in {"event_store_event_id_key", "uq_event_store_event_id"}:
        return True
    orig_message = str(orig).lower() if orig is not None else ""
    if (
        getattr(orig, "pgcode", None) == "23505"
        and "event_store" in orig_message
        and "event_id" in orig_message
    ):
        return True
    message = orig_message
    return (
        "unique" in message
        and "event_store" in message
        and "event_id" in message
    )


async def ensure_run_for_event(session, envelope: EventEnvelope) -> None:
    result = await session.execute(select(runs.c.id).where(runs.c.id == envelope.run_id))
    if result.one_or_none() is not None:
        return

    now = datetime.now(timezone.utc)
    await session.execute(
        insert(runs).values(
            id=envelope.run_id,
            job_id=envelope.job_id,
            program_id=envelope.program_id,
            event_name=envelope.event,
            trigger_event_id=envelope.causation_id or envelope.event_id,
            status=ExecutionStatus.QUEUED.value,
            attempt=1,
            created_at=now,
            updated_at=now,
        )
    )


class EventStore:
    """Durable event write model independent from dispatch delivery."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def record_event(self, envelope: EventEnvelope) -> None:
        async with self.session_factory() as session:
            try:
                await ensure_run_for_event(session, envelope)
                await insert_event_store_row(session, envelope)
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if not is_duplicate_event_integrity_error(exc):
                    raise
