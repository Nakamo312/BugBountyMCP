from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.adapters.orm import (
    event_dispatches,
    event_store,
    programs,
)
from api.infrastructure.orchestration.dispatch_store import DispatchStore


pytestmark = pytest.mark.integration


async def _seed_dispatch(session_factory: async_sessionmaker) -> tuple:
    program_id = uuid4()
    event_id = uuid4()
    dispatch_id = uuid4()
    correlation_id = uuid4()
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        await session.execute(
            insert(programs).values(
                id=program_id,
                name=f"outbox-{program_id}",
            )
        )
        await session.execute(
            insert(event_store).values(
                id=uuid4(),
                event_id=event_id,
                event_type="httpx_scan_requested",
                program_id=program_id,
                job_id=None,
                run_id=None,
                correlation_id=correlation_id,
                causation_id=None,
                source="integration-test",
                profile="safe-web-probe",
                confidence=1.0,
                payload={
                    "targets": ["https://example.com"],
                    "action_id": str(uuid4()),
                },
                created_at=now,
            )
        )
        await session.execute(
            insert(event_dispatches).values(
                id=dispatch_id,
                event_id=event_id,
                destination="rabbitmq",
                routing_key="enumeration.httpx_scan_requested",
                status="pending",
                attempts=0,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    return program_id, event_id, dispatch_id


@pytest.mark.asyncio
async def test_concurrent_dispatchers_claim_one_outbox_delivery_once(
    integration_async_engine,
) -> None:
    session_factory = async_sessionmaker(
        integration_async_engine,
        expire_on_commit=False,
    )
    _, event_id, dispatch_id = await _seed_dispatch(session_factory)
    store = DispatchStore(session_factory)

    first, second = await asyncio.gather(
        store.claim_dispatches(
            destination="rabbitmq",
            dispatcher_id="dispatcher-a",
            batch_size=1,
            lease_ttl_seconds=30,
        ),
        store.claim_dispatches(
            destination="rabbitmq",
            dispatcher_id="dispatcher-b",
            batch_size=1,
            lease_ttl_seconds=30,
        ),
    )

    claimed = [record for records in (first, second) for record in records]
    assert len(claimed) == 1
    assert claimed[0].dispatch_id == dispatch_id
    assert claimed[0].event_id == event_id


@pytest.mark.asyncio
async def test_failed_outbox_delivery_is_retryable_and_keeps_original_event(
    integration_async_engine,
) -> None:
    session_factory = async_sessionmaker(
        integration_async_engine,
        expire_on_commit=False,
    )
    _, event_id, dispatch_id = await _seed_dispatch(session_factory)
    store = DispatchStore(session_factory)

    claimed = await store.claim_dispatches(
        destination="rabbitmq",
        dispatcher_id="dispatcher-failing",
        batch_size=1,
        lease_ttl_seconds=30,
    )
    assert len(claimed) == 1

    changed = await store.mark_failed(
        dispatch_id=dispatch_id,
        dispatcher_id="dispatcher-failing",
        error="rabbit unavailable",
        current_attempts=claimed[0].attempts,
        max_attempts=3,
        retry_delay_seconds=60,
    )
    assert changed is True

    async with session_factory() as session:
        row = (
            await session.execute(
                select(
                    event_dispatches.c.status,
                    event_dispatches.c.attempts,
                    event_dispatches.c.last_error,
                    event_dispatches.c.event_id,
                ).where(event_dispatches.c.id == dispatch_id)
            )
        ).mappings().one()
        assert row["status"] == "failed"
        assert row["attempts"] == 1
        assert row["last_error"] == "rabbit unavailable"
        assert row["event_id"] == event_id

        await session.execute(
            update(event_dispatches)
            .where(event_dispatches.c.id == dispatch_id)
            .values(available_at=datetime.now(timezone.utc))
        )
        await session.commit()

    retried = await store.claim_dispatches(
        destination="rabbitmq",
        dispatcher_id="dispatcher-retry",
        batch_size=1,
        lease_ttl_seconds=30,
    )
    assert len(retried) == 1
    assert retried[0].event_id == event_id
    assert retried[0].attempts == 1
