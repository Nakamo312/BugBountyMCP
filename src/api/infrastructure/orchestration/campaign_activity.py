"""Read-model query helpers for campaign lifecycle activity."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select

from api.application.campaign_lifecycle import CampaignActivityState
from api.application.contracts import ExecutionStatus
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


def campaign_activity_query(*, program_id: uuid.UUID, campaign_id: uuid.UUID):
    campaign_runs = runs.join(jobs, runs.c.job_id == jobs.c.id)
    active_runs, dead_runs = _run_count_subqueries(
        campaign_id=campaign_id,
        campaign_runs=campaign_runs,
    )
    pending_dispatches = _pending_dispatches_subquery(campaign_id=campaign_id)
    projection_counts = _projection_count_subqueries(program_id=program_id)
    last_activity_at = _last_activity_at_expr(
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


def _campaign_events_predicate(*, campaign_id: uuid.UUID):
    return event_store.c.payload["campaign_id"].as_string() == str(campaign_id)


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
            _campaign_events_predicate(campaign_id=campaign_id),
            event_dispatches.c.status.in_(["pending", "locked", "failed"]),
        )
        .scalar_subquery()
    )


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
                projection_watermarks.c.source_watermark
                != projection_watermarks.c.applied_watermark,
            ),
        )
        .scalar_subquery()
    )
    return {
        "pending_projection_events": pending_projection_events,
        "pending_graph_batches": pending_graph_batches,
        "projection_lag_count": projection_lag_count,
    }


def _last_activity_at_expr(*, campaign_id: uuid.UUID, campaign_runs):
    campaign_events = _campaign_events_predicate(campaign_id=campaign_id)
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


def campaign_activity_from_row(row: Mapping[str, Any]) -> CampaignActivityState:
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
