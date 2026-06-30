"""Scenario-owned persistence for campaign lifecycle and activity state."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.campaign_lifecycle import (
    CampaignActivityState,
    CampaignLifecycleDecision,
    TERMINAL_CAMPAIGN_STATUSES,
    evaluate_campaign_lifecycle,
)
from api.application.contracts import ExecutionStatus, ResolvedActionCommand
from api.config import Settings
from api.infrastructure.adapters.orm import (
    campaigns,
    event_dispatches,
    event_store,
    graph_fact_batches,
    graph_projection_events,
    jobs,
    projection_watermarks,
    runs,
)


class CampaignStateStore:
    """Durable write/read model for campaign lifecycle state."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        settings: Settings | None = None,
    ):
        self.session_factory = session_factory
        self.settings = settings or Settings()

    @staticmethod
    def activity_query(*, program_id: uuid.UUID, campaign_id: uuid.UUID):
        campaign_runs = runs.join(jobs, runs.c.job_id == jobs.c.id)
        active_runs, dead_runs = CampaignStateStore._run_count_subqueries(
            campaign_id=campaign_id,
            campaign_runs=campaign_runs,
        )
        pending_dispatches = CampaignStateStore._pending_dispatches_subquery(
            campaign_id=campaign_id,
        )
        projection_counts = CampaignStateStore._projection_count_subqueries(
            program_id=program_id,
        )
        last_activity_at = CampaignStateStore._last_activity_at_expr(
            campaign_id=campaign_id,
            campaign_runs=campaign_runs,
        )
        return select(
            campaigns.c.id.label("campaign_id"),
            campaigns.c.program_id,
            campaigns.c.status.label("current_status"),
            campaigns.c.runs_consumed,
            active_runs.label("active_runs"),
            pending_dispatches.label("pending_dispatches"),
            projection_counts["pending_projection_events"].label("pending_projection_events"),
            projection_counts["pending_graph_batches"].label("pending_graph_batches"),
            projection_counts["projection_lag_count"].label("projection_lag_count"),
            dead_runs.label("dead_runs"),
            last_activity_at.label("last_activity_at"),
        ).where(campaigns.c.id == campaign_id, campaigns.c.program_id == program_id)

    @staticmethod
    def _run_count_subqueries(*, campaign_id: uuid.UUID, campaign_runs):
        active_runs = (
            select(func.count())
            .select_from(campaign_runs)
            .where(
                jobs.c.campaign_id == campaign_id,
                runs.c.status.in_(
                    [
                        ExecutionStatus.QUEUED.value,
                        ExecutionStatus.LEASED.value,
                        ExecutionStatus.RUNNING.value,
                        ExecutionStatus.FLUSHING.value,
                        ExecutionStatus.FAILED.value,
                    ]
                ),
            )
            .scalar_subquery()
        )
        dead_runs = (
            select(func.count())
            .select_from(campaign_runs)
            .where(
                jobs.c.campaign_id == campaign_id,
                runs.c.status == ExecutionStatus.DEAD.value,
            )
            .scalar_subquery()
        )
        return active_runs, dead_runs

    @staticmethod
    def _campaign_events_predicate(*, campaign_id: uuid.UUID):
        return event_store.c.payload["campaign_id"].as_string() == str(campaign_id)

    @staticmethod
    def _pending_dispatches_subquery(*, campaign_id: uuid.UUID):
        return (
            select(func.count())
            .select_from(
                event_dispatches.join(
                    event_store,
                    event_dispatches.c.event_id == event_store.c.event_id,
                )
            )
            .where(
                CampaignStateStore._campaign_events_predicate(campaign_id=campaign_id),
                event_dispatches.c.status.in_(["pending", "locked", "failed"]),
            )
            .scalar_subquery()
        )

    @staticmethod
    def _projection_count_subqueries(*, program_id: uuid.UUID) -> dict[str, Any]:
        pending_projection_events = (
            select(func.count())
            .select_from(graph_projection_events)
            .where(
                graph_projection_events.c.program_id == program_id,
                graph_projection_events.c.status.in_(["pending", "locked", "failed"]),
            )
            .scalar_subquery()
        )
        pending_graph_batches = (
            select(func.count())
            .select_from(graph_fact_batches)
            .where(
                graph_fact_batches.c.program_id == program_id,
                graph_fact_batches.c.status.in_(["pending", "locked", "failed"]),
            )
            .scalar_subquery()
        )
        projection_lag_count = (
            select(func.count())
            .select_from(projection_watermarks)
            .where(
                projection_watermarks.c.program_id == program_id,
                or_(
                    projection_watermarks.c.status != "ready",
                    projection_watermarks.c.lag_count > 0,
                    projection_watermarks.c.applied_watermark.is_(None),
                    projection_watermarks.c.source_watermark != projection_watermarks.c.applied_watermark,
                ),
            )
            .scalar_subquery()
        )
        return {
            "pending_projection_events": pending_projection_events,
            "pending_graph_batches": pending_graph_batches,
            "projection_lag_count": projection_lag_count,
        }

    @staticmethod
    def _last_activity_at_expr(*, campaign_id: uuid.UUID, campaign_runs):
        campaign_events = CampaignStateStore._campaign_events_predicate(
            campaign_id=campaign_id,
        )
        last_event_at = select(func.max(event_store.c.created_at)).where(campaign_events).scalar_subquery()
        last_run_at = (
            select(func.max(runs.c.updated_at))
            .select_from(campaign_runs)
            .where(jobs.c.campaign_id == campaign_id)
            .scalar_subquery()
        )
        return func.greatest(
            campaigns.c.created_at,
            func.coalesce(last_event_at, campaigns.c.created_at),
            func.coalesce(last_run_at, campaigns.c.created_at),
        )

    @staticmethod
    def activity_from_row(row: Mapping[str, Any]) -> CampaignActivityState:
        return CampaignActivityState(
            campaign_id=row["campaign_id"],
            program_id=row["program_id"],
            current_status=str(row["current_status"]),
            runs_consumed=int(row["runs_consumed"] or 0),
            active_runs=int(row["active_runs"] or 0),
            pending_dispatches=int(row["pending_dispatches"] or 0),
            pending_projection_events=int(row["pending_projection_events"] or 0),
            pending_graph_batches=int(row["pending_graph_batches"] or 0),
            projection_lag_count=int(row["projection_lag_count"] or 0),
            dead_runs=int(row["dead_runs"] or 0),
            last_activity_at=row["last_activity_at"],
        )

    async def get_campaign_activity(
        self,
        *,
        program_id: uuid.UUID,
        campaign_id: uuid.UUID,
    ) -> CampaignActivityState | None:
        query = self.activity_query(program_id=program_id, campaign_id=campaign_id)
        async with self.session_factory() as session:
            result = await session.execute(query)
            row = result.mappings().one_or_none()
        return self.activity_from_row(row) if row is not None else None

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

    @staticmethod
    def validate_terminal_campaign_status(status: str) -> str:
        if status not in TERMINAL_CAMPAIGN_STATUSES:
            raise ValueError(f"Invalid terminal campaign status: {status}")
        return status

    async def mark_campaign_terminal(self, *, campaign_id: uuid.UUID, status: str) -> bool:
        status = self.validate_terminal_campaign_status(status)
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
                job_status = ExecutionStatus.CANCELLED.value if status == "cancelled" else ExecutionStatus.FAILED.value
                await session.execute(
                    update(jobs)
                    .where(
                        jobs.c.campaign_id == campaign_id,
                        jobs.c.status.in_([ExecutionStatus.QUEUED.value, ExecutionStatus.RUNNING.value]),
                    )
                    .values(status=job_status, updated_at=now)
                )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def upsert_campaign(self, session, action: ResolvedActionCommand, now: datetime) -> None:
        stmt = pg_insert(campaigns).values(
            id=action.campaign_id,
            program_id=action.program_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            status="created",
            metadata=action.metadata,
            max_runs=self.settings.CAMPAIGN_MAX_RUNS,
            max_targets=self.settings.CAMPAIGN_MAX_TARGETS,
            runs_consumed=0,
            targets_consumed=0,
            token_capacity=self.settings.CAMPAIGN_TOKEN_CAPACITY,
            tokens_available=self.settings.CAMPAIGN_TOKEN_CAPACITY,
            token_refill_per_second=self.settings.CAMPAIGN_TOKEN_REFILL_PER_SECOND,
            tokens_refilled_at=now,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[campaigns.c.id],
            set_={
                "updated_at": now,
                "correlation_id": action.correlation_id,
                "workflow_id": action.workflow_id,
            },
        )
        await session.execute(stmt)

    @staticmethod
    async def activate_campaign(
        session,
        *,
        campaign_id: uuid.UUID,
        status: str,
        now: datetime,
    ) -> None:
        await session.execute(
            update(campaigns)
            .where(
                campaigns.c.id == campaign_id,
                campaigns.c.status.notin_(TERMINAL_CAMPAIGN_STATUSES),
            )
            .values(status=status, updated_at=now)
        )


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
