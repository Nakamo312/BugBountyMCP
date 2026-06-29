"""SQLAlchemy query builders for durable pipeline metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, or_, select

from api.infrastructure.adapters.orm import runs


def with_program_filter(query, program_id: UUID | None):
    if program_id is None:
        return query
    return query.where(runs.c.program_id == program_id)


def run_state_query(*, program_id: UUID | None):
    query = (
        select(
            runs.c.node_id,
            runs.c.status,
            runs.c.execution_mode,
            runs.c.terminal_outcome,
            runs.c.needs_reconcile,
            func.count().label("count"),
        )
        .group_by(
            runs.c.node_id,
            runs.c.status,
            runs.c.execution_mode,
            runs.c.terminal_outcome,
            runs.c.needs_reconcile,
        )
        .order_by(runs.c.node_id, runs.c.status)
    )
    return with_program_filter(query, program_id)


def scheduled_queue_query(*, program_id: UUID | None):
    query = (
        select(runs.c.node_id, func.count().label("count"))
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "queued",
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)


def scheduled_state_query(*, program_id: UUID | None):
    query = (
        select(
            runs.c.node_id,
            runs.c.status,
            func.count().label("count"),
        )
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status.in_(["queued", "leased", "running", "flushing"]),
            runs.c.terminal_outcome.is_(None),
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id, runs.c.status)
        .order_by(runs.c.node_id, runs.c.status)
    )
    return with_program_filter(query, program_id)


def scheduled_state_oldest_age_query(*, program_id: UUID | None):
    state_started_at = case(
        (runs.c.status == "leased", runs.c.leased_at),
        (runs.c.status == "running", runs.c.started_at),
        (runs.c.status == "flushing", runs.c.flushing_at),
        else_=runs.c.created_at,
    )
    oldest_age = func.extract(
        "epoch",
        func.now()
        - func.min(func.coalesce(state_started_at, runs.c.updated_at, runs.c.created_at)),
    )
    query = (
        select(
            runs.c.node_id,
            runs.c.status,
            oldest_age.label("oldest_age_seconds"),
        )
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status.in_(["queued", "leased", "running", "flushing"]),
            runs.c.terminal_outcome.is_(None),
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id, runs.c.status)
        .order_by(runs.c.node_id, runs.c.status)
    )
    return with_program_filter(query, program_id)


def scheduled_work_dedup_query(*, program_id: UUID | None):
    query = (
        select(
            runs.c.node_id,
            func.sum(runs.c.coalesced_trigger_count).label("count"),
        )
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.coalesced_trigger_count > 0,
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)


def scheduled_leased_query(*, program_id: UUID | None):
    query = (
        select(runs.c.node_id, func.count().label("count"))
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "leased",
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)


def retry_due_query(*, program_id: UUID | None):
    now = datetime.now(timezone.utc)
    query = (
        select(
            runs.c.node_id,
            runs.c.retry_reason,
            func.count().label("count"),
        )
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "failed",
            runs.c.retry_reason.is_not(None),
            runs.c.needs_reconcile.is_(False),
            or_(runs.c.next_retry_at.is_(None), runs.c.next_retry_at <= now),
        )
        .group_by(runs.c.node_id, runs.c.retry_reason)
        .order_by(runs.c.node_id, runs.c.retry_reason)
    )
    return with_program_filter(query, program_id)


def reconcile_query(*, program_id: UUID | None):
    query = (
        select(
            runs.c.node_id,
            runs.c.reconcile_reason,
            func.count().label("count"),
        )
        .where(runs.c.needs_reconcile.is_(True))
        .group_by(runs.c.node_id, runs.c.reconcile_reason)
        .order_by(runs.c.node_id, runs.c.reconcile_reason)
    )
    return with_program_filter(query, program_id)


def duration_query(*, program_id: UUID | None):
    duration_seconds = func.extract("epoch", runs.c.finished_at - runs.c.started_at)
    query = (
        select(
            runs.c.node_id,
            runs.c.terminal_outcome,
            func.count().label("count"),
            func.sum(duration_seconds).label("duration_seconds_sum"),
        )
        .where(
            runs.c.started_at.is_not(None),
            runs.c.finished_at.is_not(None),
        )
        .group_by(runs.c.node_id, runs.c.terminal_outcome)
        .order_by(runs.c.node_id, runs.c.terminal_outcome)
    )
    return with_program_filter(query, program_id)


def scheduled_oldest_age_query(*, program_id: UUID | None):
    oldest_age = func.extract("epoch", func.now() - func.min(runs.c.created_at))
    query = (
        select(runs.c.node_id, oldest_age.label("oldest_age_seconds"))
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "queued",
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)


def scheduled_leased_oldest_age_query(*, program_id: UUID | None):
    oldest_age = func.extract("epoch", func.now() - func.min(runs.c.leased_at))
    query = (
        select(runs.c.node_id, oldest_age.label("oldest_age_seconds"))
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "leased",
            runs.c.leased_at.is_not(None),
            runs.c.needs_reconcile.is_(False),
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)


def retry_due_oldest_age_query(*, program_id: UUID | None):
    now = datetime.now(timezone.utc)
    oldest_age = func.extract("epoch", func.now() - func.min(runs.c.next_retry_at))
    query = (
        select(
            runs.c.node_id,
            runs.c.retry_reason,
            oldest_age.label("oldest_age_seconds"),
        )
        .where(
            runs.c.execution_mode == "scheduled",
            runs.c.status == "failed",
            runs.c.retry_reason.is_not(None),
            runs.c.next_retry_at.is_not(None),
            runs.c.needs_reconcile.is_(False),
            runs.c.next_retry_at <= now,
        )
        .group_by(runs.c.node_id, runs.c.retry_reason)
        .order_by(runs.c.node_id, runs.c.retry_reason)
    )
    return with_program_filter(query, program_id)


def reconcile_oldest_age_query(*, program_id: UUID | None):
    oldest_age = func.extract("epoch", func.now() - func.min(runs.c.updated_at))
    query = (
        select(
            runs.c.node_id,
            runs.c.reconcile_reason,
            oldest_age.label("oldest_age_seconds"),
        )
        .where(runs.c.needs_reconcile.is_(True))
        .group_by(runs.c.node_id, runs.c.reconcile_reason)
        .order_by(runs.c.node_id, runs.c.reconcile_reason)
    )
    return with_program_filter(query, program_id)


def running_oldest_age_query(*, program_id: UUID | None):
    oldest_age = func.extract("epoch", func.now() - func.min(runs.c.started_at))
    query = (
        select(runs.c.node_id, oldest_age.label("oldest_age_seconds"))
        .where(
            runs.c.status == "running",
            runs.c.started_at.is_not(None),
        )
        .group_by(runs.c.node_id)
        .order_by(runs.c.node_id)
    )
    return with_program_filter(query, program_id)
