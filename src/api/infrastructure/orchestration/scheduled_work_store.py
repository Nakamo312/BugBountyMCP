"""Scenario-owned persistence for scheduled run leasing and retry requeueing."""
from __future__ import annotations

import random
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ExecutionMode,
    ExecutionStatus,
    ScheduledNodeRun,
    TerminalOutcome,
)
from api.infrastructure.adapters.orm import event_store, runs


class ScheduledWorkStore:
    """Durable work-queue state for scheduled node runs.

    Boundary rule: this store must stay limited to scheduled work queue
    lifecycle. Do not add reconciliation, campaign budget, run accounting, or
    event emission scenarios here; those belong to narrower collaborators.
    """

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def count_scheduled_active_runs_by_node(self) -> dict[str, int]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    runs.c.node_id,
                    func.count().label("count"),
                )
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.status.in_(
                        [
                            ExecutionStatus.LEASED.value,
                            ExecutionStatus.RUNNING.value,
                            ExecutionStatus.FLUSHING.value,
                        ]
                    ),
                    runs.c.terminal_outcome.is_(None),
                    runs.c.needs_reconcile.is_(False),
                )
                .group_by(runs.c.node_id)
            )
            rows = result.mappings().all()

        return {
            row["node_id"]: int(row["count"] or 0)
            for row in rows
            if row["node_id"]
        }

    async def lease_ready_scheduled_node_runs(
        self,
        *,
        node_limits: Mapping[str, int],
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> list[ScheduledNodeRun]:
        positive_limits = self._positive_node_limits(node_limits)
        if not positive_limits:
            return []

        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=max(1, lease_ttl_seconds))

        async with self.session_factory() as session:
            leased_rows = await self._select_ready_scheduled_rows(
                session,
                node_limits=positive_limits,
                now=now,
            )
            if not leased_rows:
                await session.commit()
                return []

            leased_rows.sort(key=lambda row: self._lease_sort_key(row, now=now))
            await self._mark_rows_leased(
                session,
                rows=leased_rows,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            await session.commit()

        return [self._scheduled_node_run_from_row(row) for row in leased_rows]

    @staticmethod
    def _positive_node_limits(node_limits: Mapping[str, int]) -> dict[str, int]:
        return {
            node_id: limit
            for node_id, limit in node_limits.items()
            if node_id and limit > 0
        }

    async def _select_ready_scheduled_rows(
        self,
        session,
        *,
        node_limits: Mapping[str, int],
        now: datetime,
    ) -> list:
        leased_rows = []
        for node_id, limit in sorted(node_limits.items()):
            rows = await self._select_ready_rows_for_node(
                session,
                node_id=node_id,
                limit=limit,
                now=now,
            )
            leased_rows.extend(rows)
        return leased_rows

    @staticmethod
    async def _select_ready_rows_for_node(
        session,
        *,
        node_id: str,
        limit: int,
        now: datetime,
    ) -> list:
        result = await session.execute(
            select(
                runs.c.id.label("run_id"),
                runs.c.node_id,
                runs.c.job_id,
                runs.c.program_id,
                runs.c.trigger_event_id,
                event_store.c.event_type,
                event_store.c.correlation_id,
                event_store.c.causation_id,
                event_store.c.source,
                event_store.c.profile,
                event_store.c.confidence,
                event_store.c.payload,
                runs.c.run_payload,
                runs.c.target_count,
                runs.c.next_run_at,
                runs.c.created_at,
            )
            .select_from(
                runs.join(
                    event_store,
                    runs.c.trigger_event_id == event_store.c.event_id,
                )
            )
            .where(
                runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                runs.c.status == ExecutionStatus.QUEUED.value,
                runs.c.node_id == node_id,
                runs.c.terminal_outcome.is_(None),
                runs.c.needs_reconcile.is_(False),
                or_(
                    runs.c.next_run_at.is_(None),
                    runs.c.next_run_at <= now,
                ),
            )
            .order_by(runs.c.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True, of=runs)
        )
        return result.mappings().all()

    @staticmethod
    def _lease_sort_key(row, *, now: datetime):
        return (
            row.get("next_run_at") or row.get("created_at") or now,
            row.get("created_at") or now,
            str(row["run_id"]),
        )

    @staticmethod
    async def _mark_rows_leased(
        session,
        *,
        rows,
        lease_owner: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> None:
        await session.execute(
            update(runs)
            .where(
                runs.c.id.in_([row["run_id"] for row in rows]),
                runs.c.status == ExecutionStatus.QUEUED.value,
            )
            .values(
                status=ExecutionStatus.LEASED.value,
                leased_at=now,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
        )

    async def recover_stale_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.status == ExecutionStatus.LEASED.value,
                    runs.c.lease_expires_at.is_not(None),
                    runs.c.lease_expires_at <= now,
                )
                .values(
                    status=ExecutionStatus.QUEUED.value,
                    leased_at=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    async def fail_stale_scheduled_active_runs(
        self,
        *,
        running_timeout_seconds: int,
        flushing_timeout_seconds: int,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        running_cutoff = now - timedelta(seconds=max(1, running_timeout_seconds))
        flushing_cutoff = now - timedelta(seconds=max(1, flushing_timeout_seconds))

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.terminal_outcome.is_(None),
                    runs.c.needs_reconcile.is_(False),
                    or_(
                        self._stale_running_predicate(running_cutoff),
                        self._stale_flushing_predicate(flushing_cutoff),
                    ),
                )
                .values(
                    status=ExecutionStatus.FAILED.value,
                    terminal_outcome=TerminalOutcome.TOOL_FAILED.value,
                    error="Marked failed: stale scheduled active run exceeded timeout",
                    needs_reconcile=False,
                    reconcile_reason=None,
                    lease_owner=None,
                    leased_at=None,
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    def _stale_running_predicate(cutoff: datetime):
        return (runs.c.status == ExecutionStatus.RUNNING.value) & (
            or_(runs.c.started_at.is_(None), runs.c.started_at <= cutoff)
        )

    @staticmethod
    def _stale_flushing_predicate(cutoff: datetime):
        return (runs.c.status == ExecutionStatus.FLUSHING.value) & (
            or_(runs.c.flushing_at.is_(None), runs.c.flushing_at <= cutoff)
        )

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
                retry_policy = self._retry_policy_values(policy)
                if retry_policy is None:
                    continue

                run_ids = await self._select_retryable_run_ids(
                    session,
                    node_id=node_id,
                    retry_policy=retry_policy,
                    limit=requeue_limit,
                    now=now,
                )
                await self._requeue_run_ids(
                    session,
                    run_ids=run_ids,
                    retry_reason=retry_policy.terminal_outcomes[0],
                    retry_jitter_seconds=jitter_seconds,
                    now=now,
                )
                requeued += len(run_ids)

                exhausted_run_ids = await self._select_exhausted_retry_run_ids(
                    session,
                    node_id=node_id,
                    retry_policy=retry_policy,
                    now=now,
                )
                await self._mark_exhausted_runs_dead(
                    session,
                    run_ids=exhausted_run_ids,
                    retry_reason=retry_policy.terminal_outcomes[0],
                    now=now,
                )

            await session.commit()

        return requeued

    @staticmethod
    def _retry_policy_values(policy: dict) -> "_RetryPolicy | None":
        max_attempts = int(policy.get("max_attempts", 1))
        terminal_outcomes = list(policy.get("terminal_outcomes") or [])
        if max_attempts <= 1 or not terminal_outcomes:
            return None
        return _RetryPolicy(max_attempts=max_attempts, terminal_outcomes=terminal_outcomes)

    @staticmethod
    async def _select_retryable_run_ids(
        session,
        *,
        node_id: str,
        retry_policy: "_RetryPolicy",
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

    @staticmethod
    async def _requeue_run_ids(
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
                    next_run_at=_jittered_next_run_at(
                        now=now,
                        jitter_seconds=retry_jitter_seconds,
                    ),
                    retry_reason=retry_reason,
                    updated_at=now,
                )
            )

    @staticmethod
    async def _select_exhausted_retry_run_ids(
        session,
        *,
        node_id: str,
        retry_policy: "_RetryPolicy",
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

    @staticmethod
    async def _mark_exhausted_runs_dead(
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

    @staticmethod
    def _scheduled_node_run_from_row(row) -> ScheduledNodeRun:
        event = dict(row.get("run_payload") or row["payload"] or {})
        event.update(
            {
                "event": row["event_type"],
                "event_id": str(row["trigger_event_id"]),
                "job_id": str(row["job_id"]),
                "program_id": str(row["program_id"]),
                "run_id": str(row["run_id"]),
                "correlation_id": str(row["correlation_id"]),
                "source": row["source"],
                "confidence": row["confidence"],
            }
        )
        if row["causation_id"] is not None:
            event["causation_id"] = str(row["causation_id"])
        if row["profile"] is not None:
            event["profile"] = row["profile"]

        return ScheduledNodeRun(
            run_id=row["run_id"],
            node_id=row["node_id"],
            event=event,
        )


@dataclass(frozen=True)
class _RetryPolicy:
    max_attempts: int
    terminal_outcomes: list[str]


def _jittered_next_run_at(*, now: datetime, jitter_seconds: float) -> datetime | None:
    if jitter_seconds <= 0:
        return None
    return now + timedelta(seconds=random.uniform(0.0, jitter_seconds))
