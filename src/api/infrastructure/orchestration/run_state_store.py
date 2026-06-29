"""Runner-owned state transitions for orchestration runs."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode, ExecutionStatus, TerminalOutcome
from api.infrastructure.adapters.orm import runs


class RunStateStore:
    """Durable runner state transitions for already-created runs."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def mark_run_started(
        self,
        *,
        run_id: uuid.UUID,
        node_id: str,
        event_name: str | None,
        trigger_event_id: uuid.UUID | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        values = {
            "node_id": node_id,
            "event_name": event_name,
            "trigger_event_id": trigger_event_id,
            "status": ExecutionStatus.RUNNING.value,
            "started_at": now,
            "scanner_started_at": now,
            "leased_at": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": now,
            "error": None,
        }

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(self._scheduled_guard(ExecutionStatus.LEASED))
                .values(**values)
            )
            await session.commit()

        return _single_row_updated(result)

    async def mark_run_flushing(self, *, run_id: uuid.UUID) -> bool:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(self._scheduled_guard(ExecutionStatus.RUNNING))
                .values(status=ExecutionStatus.FLUSHING.value, flushing_at=now, updated_at=now)
            )
            await session.commit()

        return _single_row_updated(result)

    async def mark_run_finished(
        self,
        *,
        run_id: uuid.UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> bool:
        self._validate_terminal_status(status)
        now = datetime.now(timezone.utc)
        retry_values = retry_values_for_terminal_status(
            now=now,
            status=status,
            terminal_outcome=terminal_outcome,
            retry_policy=retry_policy,
        )

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(self._scheduled_guard(*self._allowed_source_statuses(status)))
                .values(
                    status=status.value,
                    finished_at=now,
                    updated_at=now,
                    error=error,
                    terminal_outcome=(
                        terminal_outcome.value if terminal_outcome is not None else None
                    ),
                    **retry_values,
                )
            )
            await session.commit()

        return _single_row_updated(result)

    async def mark_run_needs_reconcile(self, *, run_id: uuid.UUID, reason: str) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(needs_reconcile=True, reconcile_reason=reason, updated_at=now)
            )
            await session.commit()

    async def clear_run_reconcile(self, *, run_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(needs_reconcile=False, reconcile_reason=None, updated_at=now)
            )
            await session.commit()

    @staticmethod
    def _validate_terminal_status(status: ExecutionStatus) -> None:
        if status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.DEAD,
            ExecutionStatus.CANCELLED,
        }:
            raise ValueError(f"Invalid terminal run status: {status}")

    @staticmethod
    def _allowed_source_statuses(status: ExecutionStatus) -> list[ExecutionStatus]:
        if status == ExecutionStatus.COMPLETED:
            return [ExecutionStatus.FLUSHING]
        if status == ExecutionStatus.FAILED:
            return [ExecutionStatus.RUNNING, ExecutionStatus.FLUSHING]
        if status == ExecutionStatus.DEAD:
            return [ExecutionStatus.FAILED]
        if status == ExecutionStatus.CANCELLED:
            return [
                ExecutionStatus.QUEUED,
                ExecutionStatus.LEASED,
                ExecutionStatus.RUNNING,
                ExecutionStatus.FLUSHING,
            ]
        return []

    @staticmethod
    def _scheduled_guard(*allowed_statuses: ExecutionStatus):
        return or_(
            runs.c.execution_mode != ExecutionMode.SCHEDULED.value,
            runs.c.status.in_([status.value for status in allowed_statuses]),
        )


def retry_values_for_terminal_status(
    *,
    now: datetime,
    status: ExecutionStatus,
    terminal_outcome: TerminalOutcome | None,
    retry_policy: dict | None,
) -> dict:
    """Return retry scheduling fields for a terminal run transition."""
    if status != ExecutionStatus.FAILED or terminal_outcome is None or not retry_policy:
        return {"next_retry_at": None}

    terminal_outcomes = set(retry_policy.get("terminal_outcomes") or [])
    max_attempts = int(retry_policy.get("max_attempts", 1))
    if terminal_outcome.value not in terminal_outcomes or max_attempts <= 1:
        return {"next_retry_at": None}

    backoff_seconds = float(retry_policy.get("backoff_seconds", 0) or 0)
    return {
        "next_retry_at": now + timedelta(seconds=max(0, backoff_seconds)),
        "retry_reason": terminal_outcome.value,
    }


def _single_row_updated(result) -> bool:
    return int(getattr(result, "rowcount", 0) or 0) == 1
