"""Scheduled run retry requeue transactions."""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode, ExecutionStatus
from api.infrastructure.adapters.orm import runs


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    terminal_outcomes: list[str]


class ScheduledRetryStore:
    """Requeue retryable scheduled runs and mark exhausted retries dead."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
        max_requeues_per_node: int | None = None,
        retry_jitter_seconds: float = 0.0,
    ) -> int:
        now = datetime.now(timezone.utc)
        requeued = 0
        requeue_limit = int(max_requeues_per_node or 0)
        jitter_seconds = max(float(retry_jitter_seconds or 0.0), 0.0)

        async with self.session_factory() as session:
            for node_id, policy in retry_policies.items():
                retry_policy = retry_policy_values(policy)
                if retry_policy is None:
                    continue

                run_ids = await select_retryable_run_ids(
                    session,
                    node_id=node_id,
                    retry_policy=retry_policy,
                    limit=requeue_limit,
                    now=now,
                )
                await requeue_run_ids(
                    session,
                    run_ids=run_ids,
                    retry_reason=retry_policy.terminal_outcomes[0],
                    retry_jitter_seconds=jitter_seconds,
                    now=now,
                )
                requeued += len(run_ids)

                exhausted_run_ids = await select_exhausted_retry_run_ids(
                    session,
                    node_id=node_id,
                    retry_policy=retry_policy,
                    now=now,
                )
                await mark_exhausted_runs_dead(
                    session,
                    run_ids=exhausted_run_ids,
                    retry_reason=retry_policy.terminal_outcomes[0],
                    now=now,
                )

            await session.commit()

        return requeued


def retry_policy_values(policy: dict) -> RetryPolicy | None:
    max_attempts = int(policy.get("max_attempts", 1))
    terminal_outcomes = list(policy.get("terminal_outcomes") or [])
    if max_attempts <= 1 or not terminal_outcomes:
        return None
    return RetryPolicy(max_attempts=max_attempts, terminal_outcomes=terminal_outcomes)


async def select_retryable_run_ids(
    session,
    *,
    node_id: str,
    retry_policy: RetryPolicy,
    limit: int,
    now: datetime,
) -> list[uuid.UUID]:
    retry_query = (
        select(runs.c.id)
        .where(
            runs.c.node_id == node_id,
            runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
            runs.c.status == ExecutionStatus.FAILED.value,
            runs.c.terminal_outcome.in_(retry_policy.terminal_outcomes),
            runs.c.attempt < retry_policy.max_attempts,
            runs.c.needs_reconcile.is_(False),
            or_(runs.c.next_retry_at.is_(None), runs.c.next_retry_at <= now),
        )
        .order_by(runs.c.updated_at.asc(), runs.c.id.asc())
    )
    if limit > 0:
        retry_query = retry_query.limit(limit)

    result = await session.execute(retry_query)
    return [row["id"] if isinstance(row, dict) else row[0] for row in result.all()]


async def requeue_run_ids(
    session,
    *,
    run_ids: list[uuid.UUID],
    retry_reason: str,
    retry_jitter_seconds: float,
    now: datetime,
) -> None:
    for run_id in run_ids:
        await session.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                status=ExecutionStatus.QUEUED.value,
                attempt=runs.c.attempt + 1,
                leased_at=None,
                lease_owner=None,
                lease_expires_at=None,
                started_at=None,
                scanner_started_at=None,
                flushing_at=None,
                finished_at=None,
                terminal_outcome=None,
                error=None,
                next_retry_at=None,
                next_run_at=jittered_next_run_at(
                    now=now,
                    jitter_seconds=retry_jitter_seconds,
                ),
                retry_reason=retry_reason,
                updated_at=now,
            )
        )


async def select_exhausted_retry_run_ids(
    session,
    *,
    node_id: str,
    retry_policy: RetryPolicy,
    now: datetime,
) -> list[uuid.UUID]:
    result = await session.execute(
        select(runs.c.id)
        .where(
            runs.c.node_id == node_id,
            runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
            runs.c.status == ExecutionStatus.FAILED.value,
            runs.c.terminal_outcome.in_(retry_policy.terminal_outcomes),
            runs.c.attempt >= retry_policy.max_attempts,
            runs.c.needs_reconcile.is_(False),
            or_(runs.c.next_retry_at.is_(None), runs.c.next_retry_at <= now),
        )
        .order_by(runs.c.updated_at.asc(), runs.c.id.asc())
    )
    return [row["id"] if isinstance(row, dict) else row[0] for row in result.all()]


async def mark_exhausted_runs_dead(
    session,
    *,
    run_ids: list[uuid.UUID],
    retry_reason: str,
    now: datetime,
) -> None:
    if not run_ids:
        return
    await session.execute(
        update(runs)
        .where(runs.c.id.in_(run_ids))
        .values(
            status=ExecutionStatus.DEAD.value,
            next_retry_at=None,
            retry_reason=retry_reason,
            updated_at=now,
        )
    )


def jittered_next_run_at(*, now: datetime, jitter_seconds: float) -> datetime | None:
    if jitter_seconds <= 0:
        return None
    return now + timedelta(seconds=random.uniform(0.0, jitter_seconds))
