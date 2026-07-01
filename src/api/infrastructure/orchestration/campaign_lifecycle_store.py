"""Session boundary for campaign lifecycle reconciliation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.campaign_lifecycle import (
    CampaignActivityState,
    CampaignLifecycleDecision,
    TERMINAL_CAMPAIGN_STATUSES,
    evaluate_campaign_lifecycle,
)
from api.application.contracts import ExecutionStatus
from api.infrastructure.adapters.orm import campaigns, jobs
from api.infrastructure.orchestration.campaign_activity import (
    campaign_activity_from_row,
    campaign_activity_query,
)


class CampaignLifecycleStore:
    """Durable lifecycle read/reconcile boundary for campaign state."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def get_campaign_activity(
        self,
        *,
        program_id: uuid.UUID,
        campaign_id: uuid.UUID,
    ) -> CampaignActivityState | None:
        query = campaign_activity_query(program_id=program_id, campaign_id=campaign_id)
        async with self.session_factory() as session:
            result = await session.execute(query)
            row = result.mappings().one_or_none()
        return campaign_activity_from_row(row) if row is not None else None

    async def reconcile_campaign_lifecycle(
        self,
        *,
        program_id: uuid.UUID,
        campaign_id: uuid.UUID,
        now: datetime,
        quiet_window_seconds: float,
    ) -> CampaignLifecycleDecision | None:
        state = await self.get_campaign_activity(program_id=program_id, campaign_id=campaign_id)
        if state is None:
            return None
        decision = evaluate_campaign_lifecycle(
            state,
            now=now,
            quiet_window_seconds=quiet_window_seconds,
        )
        if decision.status != state.current_status:
            await self.persist_campaign_lifecycle(
                campaign_id=campaign_id,
                status=decision.status,
                active_runs=state.active_runs,
                now=now,
            )
        return decision

    async def reconcile_active_campaigns(
        self,
        *,
        now: datetime,
        quiet_window_seconds: float,
        limit: int,
    ) -> int:
        async with self.session_factory() as session:
            result = await session.execute(
                select(campaigns.c.id, campaigns.c.program_id)
                .where(
                    campaigns.c.status.in_(
                        ["running", "expanding", "waiting_for_projections", "quiescent"]
                    )
                )
                .order_by(campaigns.c.updated_at.asc(), campaigns.c.id.asc())
                .limit(max(1, limit))
            )
            rows = result.mappings().all()
        for row in rows:
            await self.reconcile_campaign_lifecycle(
                program_id=row["program_id"],
                campaign_id=row["id"],
                now=now,
                quiet_window_seconds=quiet_window_seconds,
            )
        return len(rows)

    async def persist_campaign_lifecycle(
        self,
        *,
        campaign_id: uuid.UUID,
        status: str,
        active_runs: int,
        now: datetime,
    ) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                update(campaigns)
                .where(
                    campaigns.c.id == campaign_id,
                    campaigns.c.status.notin_(TERMINAL_CAMPAIGN_STATUSES),
                )
                .values(status=status, updated_at=now)
            )
            await update_jobs_for_campaign_lifecycle(
                session,
                campaign_id=campaign_id,
                status=status,
                active_runs=active_runs,
                now=now,
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def mark_campaign_terminal(self, *, campaign_id: uuid.UUID, status: str) -> bool:
        status = validate_terminal_campaign_status(status)
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                update(campaigns)
                .where(
                    campaigns.c.id == campaign_id,
                    campaigns.c.status.notin_(TERMINAL_CAMPAIGN_STATUSES),
                )
                .values(status=status, updated_at=now)
            )
            if status in {"cancelled", "failed"}:
                job_status = (
                    ExecutionStatus.CANCELLED.value
                    if status == "cancelled"
                    else ExecutionStatus.FAILED.value
                )
                await session.execute(
                    update(jobs)
                    .where(
                        jobs.c.campaign_id == campaign_id,
                        jobs.c.status.in_(
                            [ExecutionStatus.QUEUED.value, ExecutionStatus.RUNNING.value]
                        ),
                    )
                    .values(status=job_status, updated_at=now)
                )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1


async def update_jobs_for_campaign_lifecycle(
    session,
    *,
    campaign_id: uuid.UUID,
    status: str,
    active_runs: int,
    now: datetime,
) -> None:
    if status in {"running", "expanding"} or active_runs > 0:
        await session.execute(
            update(jobs)
            .where(jobs.c.campaign_id == campaign_id, jobs.c.status == ExecutionStatus.QUEUED.value)
            .values(status=ExecutionStatus.RUNNING.value, updated_at=now)
        )
    elif status in {"waiting_for_projections", "quiescent"}:
        await session.execute(
            update(jobs)
            .where(
                jobs.c.campaign_id == campaign_id,
                jobs.c.status.in_([ExecutionStatus.QUEUED.value, ExecutionStatus.RUNNING.value]),
            )
            .values(status=ExecutionStatus.COMPLETED.value, updated_at=now)
        )
    elif status == "failed":
        await session.execute(
            update(jobs)
            .where(
                jobs.c.campaign_id == campaign_id,
                jobs.c.status.in_([ExecutionStatus.QUEUED.value, ExecutionStatus.RUNNING.value]),
            )
            .values(status=ExecutionStatus.FAILED.value, updated_at=now)
        )


def validate_terminal_campaign_status(status: str) -> str:
    if status not in TERMINAL_CAMPAIGN_STATUSES:
        raise ValueError(f"Invalid terminal campaign status: {status}")
    return status
