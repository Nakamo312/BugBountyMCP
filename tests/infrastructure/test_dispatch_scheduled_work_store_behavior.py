from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from api.application.contracts import ExecutionStatus
from api.infrastructure.orchestration.dispatch_store import DispatchStore
from api.infrastructure.orchestration.scheduled_work_store import (
    ScheduledWorkStore,
    _RetryPolicy,
)


class RowCountResult:
    def __init__(self, rowcount: int = 1):
        self.rowcount = rowcount


class RecordingSession:
    def __init__(self, *, rowcount: int = 1) -> None:
        self.rowcount = rowcount
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return RowCountResult(self.rowcount)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _compiled_params(statement) -> dict:
    return statement.compile(dialect=postgresql.dialect()).params


def test_dispatch_claim_predicate_reclaims_expired_locks() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pending_or_failed, expired_lock = DispatchStore._claimable_dispatch_predicates(now=now)

    expired_sql = str(expired_lock.compile(dialect=postgresql.dialect()))
    pending_sql = str(pending_or_failed.compile(dialect=postgresql.dialect()))

    assert "event_dispatches.status" in expired_sql
    assert "event_dispatches.locked_until" in expired_sql
    assert "locked_until <=" in expired_sql
    assert "event_dispatches.available_at" in pending_sql
    assert "available_at <=" in pending_sql


@pytest.mark.asyncio
async def test_dispatch_mark_failed_moves_to_dead_after_max_attempts() -> None:
    session = RecordingSession(rowcount=1)
    store = DispatchStore(lambda: session)
    dispatch_id = uuid4()

    updated = await store.mark_failed(
        dispatch_id=dispatch_id,
        dispatcher_id="dispatcher-1",
        error="boom",
        current_attempts=2,
        max_attempts=3,
        retry_delay_seconds=30,
    )

    assert updated is True
    assert session.commits == 1
    params = _compiled_params(session.statements[0])
    assert params["status"] == "dead"
    assert params["attempts"] == 3
    assert params["locked_by"] is None
    assert params["locked_until"] is None
    assert params["last_error"] == "boom"


@pytest.mark.asyncio
async def test_dispatch_mark_failed_keeps_retryable_failed_available_later() -> None:
    session = RecordingSession(rowcount=1)
    store = DispatchStore(lambda: session)

    updated = await store.mark_failed(
        dispatch_id=uuid4(),
        dispatcher_id="dispatcher-1",
        error="transient",
        current_attempts=0,
        max_attempts=3,
        retry_delay_seconds=30,
    )

    assert updated is True
    params = _compiled_params(session.statements[0])
    assert params["status"] == "failed"
    assert params["attempts"] == 1
    assert params["available_at"] > params["updated_at"]


@pytest.mark.asyncio
async def test_scheduled_ready_selection_respects_per_node_limits(monkeypatch) -> None:
    store = ScheduledWorkStore(lambda: RecordingSession())
    calls = []

    async def select_ready_for_node(session, *, node_id, limit, now):
        calls.append((node_id, limit))
        return [{"node_id": node_id, "run_id": uuid4(), "created_at": now} for _ in range(limit)]

    monkeypatch.setattr(
        ScheduledWorkStore,
        "_select_ready_rows_for_node",
        staticmethod(select_ready_for_node),
    )

    rows = await store._select_ready_scheduled_rows(
        object(),
        node_limits={"node-b": 2, "node-a": 1, "node-zero": 0},
        now=datetime.now(timezone.utc),
    )

    assert calls == [("node-a", 1), ("node-b", 2), ("node-zero", 0)]
    assert [row["node_id"] for row in rows] == ["node-a", "node-b", "node-b"]


@pytest.mark.asyncio
async def test_scheduled_requeue_increments_attempt_and_clears_terminal_fields() -> None:
    session = RecordingSession()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    await ScheduledWorkStore._requeue_run_ids(
        session,
        run_ids=[uuid4()],
        retry_reason="tool_failed",
        retry_jitter_seconds=0.0,
        now=now,
    )

    statement = session.statements[0]
    params = _compiled_params(statement)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "attempt=(runs.attempt +" in sql
    assert params["status"] == ExecutionStatus.QUEUED.value
    assert params["leased_at"] is None
    assert params["lease_owner"] is None
    assert params["lease_expires_at"] is None
    assert params["started_at"] is None
    assert params["scanner_started_at"] is None
    assert params["flushing_at"] is None
    assert params["finished_at"] is None
    assert params["terminal_outcome"] is None
    assert params["error"] is None
    assert params["next_retry_at"] is None
    assert params["next_run_at"] is None
    assert params["retry_reason"] == "tool_failed"


@pytest.mark.asyncio
async def test_scheduled_exhausted_retry_moves_to_dead() -> None:
    session = RecordingSession()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    await ScheduledWorkStore._mark_exhausted_runs_dead(
        session,
        run_ids=[uuid4()],
        retry_reason="tool_failed",
        now=now,
    )

    params = _compiled_params(session.statements[0])
    assert params["status"] == ExecutionStatus.DEAD.value
    assert params["next_retry_at"] is None
    assert params["retry_reason"] == "tool_failed"
    assert params["updated_at"] == now


def test_retry_policy_skips_non_retryable_policy() -> None:
    assert ScheduledWorkStore._retry_policy_values({"max_attempts": 1}) is None
    assert ScheduledWorkStore._retry_policy_values({"max_attempts": 3}) is None
    assert ScheduledWorkStore._retry_policy_values(
        {"max_attempts": 3, "terminal_outcomes": ["tool_failed"]}
    ) == _RetryPolicy(max_attempts=3, terminal_outcomes=["tool_failed"])
