from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode
from api.infrastructure.adapters.orm import (
    action_requests,
    campaigns,
    jobs,
    programs,
    runs,
)
from api.infrastructure.orchestration.store import OrchestrationStore


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_claims_cannot_overspend_campaign_run_budget(
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
    correlation_id = uuid4()
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        await session.execute(
            insert(programs).values(
                id=program_id,
                name=f"campaign-budget-{program_id}",
            )
        )
        await session.execute(
            insert(campaigns).values(
                id=campaign_id,
                program_id=program_id,
                correlation_id=correlation_id,
                status="created",
                metadata={},
                max_runs=1,
                max_targets=10,
                runs_consumed=0,
                targets_consumed=0,
                token_capacity=10.0,
                tokens_available=10.0,
                token_refill_per_second=1.0,
                tokens_refilled_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.execute(
            insert(action_requests).values(
                id=action_id,
                program_id=program_id,
                catalog_entry_id=None,
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
                created_at=now,
                updated_at=now,
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
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    store = OrchestrationStore(session_factory)

    async def claim(index: int):
        return await store.claim_node_run(
            claim_key=f"claim-{campaign_id}-{index}",
            job_id=job_id,
            program_id=program_id,
            node_id="httpx",
            event_name="host_discovered",
            trigger_event_id=uuid4(),
            input_fingerprint=f"input-{index}",
            target_fingerprint=f"target-{index}",
            execution_mode=ExecutionMode.SCHEDULED,
            target_count=1,
            work_key=f"work-{campaign_id}-{index}",
            campaign_id=campaign_id,
            expansion_depth=1,
            max_expansion_depth=6,
            cooldown_seconds=0,
            token_cost=1,
        )

    first, second = await asyncio.gather(claim(1), claim(2))

    assert sum(item.created for item in (first, second)) == 1
    assert {
        item.blocked_reason
        for item in (first, second)
        if item.blocked_reason is not None
    } == {"campaign_run_budget_exhausted"}

    async with session_factory() as session:
        campaign = (
            await session.execute(
                select(
                    campaigns.c.runs_consumed,
                    campaigns.c.targets_consumed,
                ).where(campaigns.c.id == campaign_id)
            )
        ).mappings().one()
        run_count = (
            await session.execute(
                select(runs.c.id).where(runs.c.job_id == job_id)
            )
        ).all()

    assert campaign["runs_consumed"] == 1
    assert campaign["targets_consumed"] == 1
    assert len(run_count) == 1
