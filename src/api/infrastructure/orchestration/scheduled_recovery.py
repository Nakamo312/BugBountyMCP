"""Scheduled run lease recovery and stale-active failure transactions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode, ExecutionStatus, TerminalOutcome
from api.infrastructure.adapters.orm import runs

STALE_ACTIVE_RUN_ERROR = "Marked failed: stale scheduled active run exceeded timeout"


class ScheduledRecoveryStore:
    """Recover expired leases and terminalize stale active scheduled runs."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

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
                        stale_running_predicate(running_cutoff),
                        stale_flushing_predicate(flushing_cutoff),
                    ),
                )
                .values(
                    status=ExecutionStatus.FAILED.value,
                    terminal_outcome=TerminalOutcome.TOOL_FAILED.value,
                    error=STALE_ACTIVE_RUN_ERROR,
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


def stale_running_predicate(cutoff: datetime):
    return (runs.c.status == ExecutionStatus.RUNNING.value) & (
        or_(runs.c.started_at.is_(None), runs.c.started_at <= cutoff)
    )


def stale_flushing_predicate(cutoff: datetime):
    return (runs.c.status == ExecutionStatus.FLUSHING.value) & (
        or_(runs.c.flushing_at.is_(None), runs.c.flushing_at <= cutoff)
    )
