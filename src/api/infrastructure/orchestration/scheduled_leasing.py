"""Scheduled run active count and lease acquisition transactions."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode, ExecutionStatus, ScheduledNodeRun
from api.infrastructure.adapters.orm import event_store, runs


class ScheduledLeaseStore:
    """Acquire and count scheduled work leases."""

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
        positive_limits = positive_node_limits(node_limits)
        if not positive_limits:
            return []

        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=max(1, lease_ttl_seconds))

        async with self.session_factory() as session:
            leased_rows = await select_ready_scheduled_rows(
                session,
                node_limits=positive_limits,
                now=now,
            )
            if not leased_rows:
                await session.commit()
                return []

            leased_rows.sort(key=lambda row: lease_sort_key(row, now=now))
            await mark_rows_leased(
                session,
                rows=leased_rows,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            await session.commit()

        return [scheduled_node_run_from_row(row) for row in leased_rows]


def positive_node_limits(node_limits: Mapping[str, int]) -> dict[str, int]:
    return {
        node_id: limit
        for node_id, limit in node_limits.items()
        if node_id and limit > 0
    }


async def select_ready_scheduled_rows(
    session,
    *,
    node_limits: Mapping[str, int],
    now: datetime,
) -> list:
    leased_rows = []
    for node_id, limit in sorted(node_limits.items()):
        rows = await select_ready_rows_for_node(
            session,
            node_id=node_id,
            limit=limit,
            now=now,
        )
        leased_rows.extend(rows)
    return leased_rows


async def select_ready_rows_for_node(
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


def lease_sort_key(row, *, now: datetime):
    return (
        row.get("next_run_at") or row.get("created_at") or now,
        row.get("created_at") or now,
        str(row["run_id"]),
    )


async def mark_rows_leased(
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


def scheduled_node_run_from_row(row) -> ScheduledNodeRun:
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
