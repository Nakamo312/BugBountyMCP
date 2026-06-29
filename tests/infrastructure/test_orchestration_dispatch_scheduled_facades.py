from __future__ import annotations

from uuid import uuid4

import pytest

from api.infrastructure.orchestration.store import OrchestrationStore


class RecordingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_dispatch_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    calls: list[tuple[str, dict]] = []

    async def claim_dispatches(**kwargs):
        calls.append(("claim_dispatches", kwargs))
        return ["claimed"]

    async def mark_sent(**kwargs):
        calls.append(("mark_sent", kwargs))
        return True

    async def mark_failed(**kwargs):
        calls.append(("mark_failed", kwargs))
        return False

    monkeypatch.setattr(store.dispatches, "claim_dispatches", claim_dispatches)
    monkeypatch.setattr(store.dispatches, "mark_sent", mark_sent)
    monkeypatch.setattr(store.dispatches, "mark_failed", mark_failed)

    dispatch_id = uuid4()
    claimed = await store.claim_dispatches(
        destination="rabbitmq",
        dispatcher_id="dispatcher-1",
        batch_size=10,
        lease_ttl_seconds=30,
    )
    sent = await store.mark_sent(
        dispatch_id=dispatch_id,
        dispatcher_id="dispatcher-1",
    )
    failed = await store.mark_failed(
        dispatch_id=dispatch_id,
        dispatcher_id="dispatcher-1",
        error="boom",
        current_attempts=1,
        max_attempts=3,
        retry_delay_seconds=5.0,
    )

    assert claimed == ["claimed"]
    assert sent is True
    assert failed is False
    assert calls == [
        (
            "claim_dispatches",
            {
                "destination": "rabbitmq",
                "dispatcher_id": "dispatcher-1",
                "batch_size": 10,
                "lease_ttl_seconds": 30,
            },
        ),
        (
            "mark_sent",
            {
                "dispatch_id": dispatch_id,
                "dispatcher_id": "dispatcher-1",
            },
        ),
        (
            "mark_failed",
            {
                "dispatch_id": dispatch_id,
                "dispatcher_id": "dispatcher-1",
                "error": "boom",
                "current_attempts": 1,
                "max_attempts": 3,
                "retry_delay_seconds": 5.0,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_scheduled_work_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    calls: list[tuple[str, dict]] = []

    async def count_scheduled_active_runs_by_node():
        calls.append(("count", {}))
        return {"node-a": 2}

    async def lease_ready_scheduled_node_runs(**kwargs):
        calls.append(("lease", kwargs))
        return ["leased"]

    async def recover_stale_leases(**kwargs):
        calls.append(("recover", kwargs))
        return 3

    async def fail_stale_scheduled_active_runs(**kwargs):
        calls.append(("fail_stale", kwargs))
        return 4

    async def requeue_retryable_node_runs(**kwargs):
        calls.append(("requeue", kwargs))
        return 5

    monkeypatch.setattr(
        store.scheduled_work,
        "count_scheduled_active_runs_by_node",
        count_scheduled_active_runs_by_node,
    )
    monkeypatch.setattr(
        store.scheduled_work,
        "lease_ready_scheduled_node_runs",
        lease_ready_scheduled_node_runs,
    )
    monkeypatch.setattr(store.scheduled_work, "recover_stale_leases", recover_stale_leases)
    monkeypatch.setattr(
        store.scheduled_work,
        "fail_stale_scheduled_active_runs",
        fail_stale_scheduled_active_runs,
    )
    monkeypatch.setattr(
        store.scheduled_work,
        "requeue_retryable_node_runs",
        requeue_retryable_node_runs,
    )

    counts = await store.count_scheduled_active_runs_by_node()
    leased = await store.lease_ready_scheduled_node_runs(
        node_limits={"node-a": 1},
        lease_owner="worker-1",
        lease_ttl_seconds=30,
    )
    recovered = await store.recover_stale_leases(now=None)
    failed = await store.fail_stale_scheduled_active_runs(
        running_timeout_seconds=60,
        flushing_timeout_seconds=30,
        now=None,
    )
    requeued = await store.requeue_retryable_node_runs(
        retry_policies={"node-a": {"max_attempts": 2}},
        max_requeues_per_node=7,
        retry_jitter_seconds=1.5,
    )

    assert counts == {"node-a": 2}
    assert leased == ["leased"]
    assert recovered == 3
    assert failed == 4
    assert requeued == 5
    assert calls == [
        ("count", {}),
        (
            "lease",
            {
                "node_limits": {"node-a": 1},
                "lease_owner": "worker-1",
                "lease_ttl_seconds": 30,
            },
        ),
        ("recover", {"now": None}),
        (
            "fail_stale",
            {
                "running_timeout_seconds": 60,
                "flushing_timeout_seconds": 30,
                "now": None,
            },
        ),
        (
            "requeue",
            {
                "retry_policies": {"node-a": {"max_attempts": 2}},
                "max_requeues_per_node": 7,
                "retry_jitter_seconds": 1.5,
            },
        ),
    ]
