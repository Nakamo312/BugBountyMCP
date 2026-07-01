from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.application.contracts import ExecutionStatus, TerminalOutcome
from api.infrastructure.orchestration.run_state_store import retry_values_for_terminal_status
from api.infrastructure.orchestration.store import OrchestrationStore


class RecordingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_action_read_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    action_id = uuid4()
    program_id = uuid4()
    calls: list[tuple[str, tuple, dict]] = []

    async def list_actions(*args, **kwargs):
        calls.append(("list_actions", args, kwargs))
        return ["action"]

    async def get_action(*args, **kwargs):
        calls.append(("get_action", args, kwargs))
        return "single-action"

    async def list_action_events(*args, **kwargs):
        calls.append(("list_action_events", args, kwargs))
        return ["event"]

    async def list_action_runs(*args, **kwargs):
        calls.append(("list_action_runs", args, kwargs))
        return ["run"]

    async def list_action_artifacts(*args, **kwargs):
        calls.append(("list_action_artifacts", args, kwargs))
        return ["artifact"]

    monkeypatch.setattr(store.action_reads, "list_actions", list_actions)
    monkeypatch.setattr(store.action_reads, "get_action", get_action)
    monkeypatch.setattr(store.action_reads, "list_action_events", list_action_events)
    monkeypatch.setattr(store.action_reads, "list_action_runs", list_action_runs)
    monkeypatch.setattr(store.action_reads, "list_action_artifacts", list_action_artifacts)

    assert await store.list_actions(status="queued", program_id=program_id, limit=5, offset=2) == [
        "action"
    ]
    assert await store.get_action(action_id) == "single-action"
    assert await store.list_action_events(action_id, limit=7, offset=3) == ["event"]
    assert await store.list_action_runs(action_id) == ["run"]
    assert await store.list_action_artifacts(action_id) == ["artifact"]

    assert calls == [
        (
            "list_actions",
            (),
            {"status": "queued", "program_id": program_id, "limit": 5, "offset": 2},
        ),
        ("get_action", (action_id,), {}),
        ("list_action_events", (action_id,), {"limit": 7, "offset": 3}),
        ("list_action_runs", (action_id,), {}),
        ("list_action_artifacts", (action_id,), {}),
    ]


@pytest.mark.asyncio
async def test_run_state_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    run_id = uuid4()
    trigger_event_id = uuid4()
    calls: list[tuple[str, dict]] = []

    async def mark_run_started(**kwargs):
        calls.append(("mark_run_started", kwargs))
        return True

    async def mark_run_flushing(**kwargs):
        calls.append(("mark_run_flushing", kwargs))
        return False

    async def mark_run_finished(**kwargs):
        calls.append(("mark_run_finished", kwargs))
        return True

    async def mark_run_needs_reconcile(**kwargs):
        calls.append(("mark_run_needs_reconcile", kwargs))

    async def clear_run_reconcile(**kwargs):
        calls.append(("clear_run_reconcile", kwargs))

    monkeypatch.setattr(store.run_states, "mark_run_started", mark_run_started)
    monkeypatch.setattr(store.run_states, "mark_run_flushing", mark_run_flushing)
    monkeypatch.setattr(store.run_states, "mark_run_finished", mark_run_finished)
    monkeypatch.setattr(store.run_states, "mark_run_needs_reconcile", mark_run_needs_reconcile)
    monkeypatch.setattr(store.run_states, "clear_run_reconcile", clear_run_reconcile)

    assert await store.mark_run_started(
        run_id=run_id,
        node_id="node-a",
        event_name="surface.changed",
        trigger_event_id=trigger_event_id,
    ) is True
    assert await store.mark_run_flushing(run_id=run_id) is False
    assert await store.mark_run_finished(
        run_id=run_id,
        status=ExecutionStatus.FAILED,
        error="boom",
        terminal_outcome=TerminalOutcome.TOOL_FAILED,
        retry_policy={"max_attempts": 2},
    ) is True
    await store.mark_run_needs_reconcile(run_id=run_id, reason="artifact-missing")
    await store.clear_run_reconcile(run_id=run_id)

    assert calls == [
        (
            "mark_run_started",
            {
                "run_id": run_id,
                "node_id": "node-a",
                "event_name": "surface.changed",
                "trigger_event_id": trigger_event_id,
            },
        ),
        ("mark_run_flushing", {"run_id": run_id}),
        (
            "mark_run_finished",
            {
                "run_id": run_id,
                "status": ExecutionStatus.FAILED,
                "error": "boom",
                "terminal_outcome": TerminalOutcome.TOOL_FAILED,
                "retry_policy": {"max_attempts": 2},
            },
        ),
        ("mark_run_needs_reconcile", {"run_id": run_id, "reason": "artifact-missing"}),
        ("clear_run_reconcile", {"run_id": run_id}),
    ]


def test_retry_values_for_terminal_status_remains_explicit_contract() -> None:
    now = datetime.now(timezone.utc)
    values = retry_values_for_terminal_status(
        now=now,
        status=ExecutionStatus.FAILED,
        terminal_outcome=TerminalOutcome.TOOL_FAILED,
        retry_policy={
            "terminal_outcomes": [TerminalOutcome.TOOL_FAILED.value],
            "max_attempts": 2,
            "backoff_seconds": 30,
        },
    )

    assert values["retry_reason"] == TerminalOutcome.TOOL_FAILED.value
    assert values["next_retry_at"] >= now
