from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.adapters.orm import (
    action_requests,
    campaigns,
    event_dispatches,
    event_store,
    jobs,
    programs,
    runs,
)
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_campaign_waits_for_outbox_then_becomes_quiescent(
    integration_async_engine,
) -> None:
    session_factory = async_sessionmaker(
        integration_async_engine,
        expire_on_commit=False,
    )
    program_id = uuid4()
    campaign_id = uuid4()
    action_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    event_id = uuid4()
    dispatch_id = uuid4()
    correlation_id = uuid4()
    created_at = datetime.now(timezone.utc) - timedelta(seconds=31)

    async with session_factory() as session:
        await session.execute(
            insert(programs).values(
                id=program_id,
                name=f"campaign-lifecycle-{program_id}",
            )
        )
        await session.execute(
            insert(campaigns).values(
                id=campaign_id,
                program_id=program_id,
                correlation_id=correlation_id,
                status="running",
                metadata={},
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.execute(
            insert(action_requests).values(
                id=action_id,
                program_id=program_id,
                kind="scan",
                capability_id="httpx",
                profile_id="safe-web-probe",
                requested_by="integration-test",
                campaign_id=campaign_id,
                correlation_id=correlation_id,
                metadata={},
                status="queued",
                request={
                    "program_id": str(program_id),
                    "catalog_id": str(uuid4()),
                    "targets": ["example.com"],
                },
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.execute(
            insert(jobs).values(
                id=job_id,
                action_id=action_id,
                program_id=program_id,
                capability_id="httpx",
                profile_id="safe-web-probe",
                status="queued",
                correlation_id=correlation_id,
                campaign_id=campaign_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.execute(
            insert(runs).values(
                id=run_id,
                job_id=job_id,
                program_id=program_id,
                status="completed",
                attempt=1,
                terminal_outcome="completed",
                created_at=created_at,
                updated_at=created_at,
                finished_at=created_at,
            )
        )
        await session.execute(
            insert(event_store).values(
                id=uuid4(),
                event_id=event_id,
                event_type="httpx_scan_requested",
                program_id=program_id,
                job_id=job_id,
                run_id=run_id,
                correlation_id=correlation_id,
                source="integration-test",
                confidence=1.0,
                payload={"campaign_id": str(campaign_id)},
                created_at=created_at,
            )
        )
        await session.execute(
            insert(event_dispatches).values(
                id=dispatch_id,
                event_id=event_id,
                destination="rabbitmq",
                routing_key="analysis.httpx_scan_requested",
                status="pending",
                attempts=0,
                available_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()

    store = CampaignStateStore(session_factory)
    now = datetime.now(timezone.utc)

    pending = await store.reconcile_campaign_lifecycle(
        program_id=program_id,
        campaign_id=campaign_id,
        now=now,
        quiet_window_seconds=30,
    )

    assert pending is not None
    assert pending.quiescent is False
    assert pending.reason == "pending_dispatch"

    async with session_factory() as session:
        await session.execute(
            update(event_dispatches)
            .where(event_dispatches.c.id == dispatch_id)
            .values(status="dispatched", dispatched_at=now, updated_at=now)
        )
        await session.commit()

    settled = await store.reconcile_campaign_lifecycle(
        program_id=program_id,
        campaign_id=campaign_id,
        now=now,
        quiet_window_seconds=30,
    )

    assert settled is not None
    assert settled.quiescent is True
    assert settled.status == "quiescent"

    async with session_factory() as session:
        status = (
            await session.execute(
                select(campaigns.c.status).where(campaigns.c.id == campaign_id)
            )
        ).scalar_one()
        job_status = (
            await session.execute(
                select(jobs.c.status).where(jobs.c.id == job_id)
            )
        ).scalar_one()

    assert status == "quiescent"
    assert job_status == "completed"
