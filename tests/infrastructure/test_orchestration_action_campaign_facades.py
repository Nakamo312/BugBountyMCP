from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.application.contracts import (
    ActionKind,
    ActionRequest,
    EventEnvelope,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.infrastructure.orchestration.store import OrchestrationStore


class RecordingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _action() -> ActionRequest:
    return ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
    )


def _decision(action: ActionRequest) -> PolicyDecision:
    return PolicyDecision(
        action_id=action.action_id,
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=action.targets,
    )


def _envelope(action: ActionRequest) -> EventEnvelope:
    return EventEnvelope(
        event="httpx_scan_requested",
        program_id=action.program_id,
        targets=action.targets,
    )


@pytest.mark.asyncio
async def test_action_command_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    calls: list[tuple[str, tuple, dict]] = []
    action = _action()
    decision = _decision(action)
    envelope = _envelope(action)
    scope_id = uuid4()

    async def record_policy_result(*args, **kwargs):
        calls.append(("record_policy_result", args, kwargs))
        return scope_id

    async def create_allowed_action(*args, **kwargs):
        calls.append(("create_allowed_action", args, kwargs))

    async def create_queued_job(*args, **kwargs):
        calls.append(("create_queued_job", args, kwargs))

    async def get_scope_id(*args, **kwargs):
        calls.append(("get_scope_id", args, kwargs))
        return scope_id

    monkeypatch.setattr(store.action_commands, "record_policy_result", record_policy_result)
    monkeypatch.setattr(store.action_commands, "create_allowed_action", create_allowed_action)
    monkeypatch.setattr(store.action_commands, "create_queued_job", create_queued_job)
    monkeypatch.setattr(store.action_commands, "get_scope_id", get_scope_id)

    assert await store.record_policy_result(action, decision) == scope_id
    await store.create_allowed_action(action, decision, envelope, scope_id=scope_id)
    await store.create_queued_job(action, envelope)
    assert await store.get_scope_id(action.action_id) == scope_id

    assert calls == [
        ("record_policy_result", (action, decision), {}),
        ("create_allowed_action", (action, decision, envelope), {"scope_id": scope_id}),
        ("create_queued_job", (action, envelope), {}),
        ("get_scope_id", (action.action_id,), {}),
    ]


@pytest.mark.asyncio
async def test_approval_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    calls: list[tuple[str, tuple, dict]] = []
    action = _action()
    decision = _decision(action)
    envelope = _envelope(action)

    async def get_action_for_approval(*args, **kwargs):
        calls.append(("get_action_for_approval", args, kwargs))
        return action, "requires_approval"

    async def approve_and_create_queued_job(*args, **kwargs):
        calls.append(("approve_and_create_queued_job", args, kwargs))
        return True

    async def reject_action(*args, **kwargs):
        calls.append(("reject_action", args, kwargs))
        return False

    monkeypatch.setattr(store.approvals, "get_action_for_approval", get_action_for_approval)
    monkeypatch.setattr(
        store.approvals,
        "approve_and_create_queued_job",
        approve_and_create_queued_job,
    )
    monkeypatch.setattr(store.approvals, "reject_action", reject_action)

    assert await store.get_action_for_approval(action.action_id) == (action, "requires_approval")
    assert await store.approve_and_create_queued_job(action, decision, envelope) is True
    assert await store.reject_action(action, decision) is False

    assert calls == [
        ("get_action_for_approval", (action.action_id,), {}),
        ("approve_and_create_queued_job", (action, decision, envelope), {}),
        ("reject_action", (action, decision), {}),
    ]


@pytest.mark.asyncio
async def test_campaign_methods_remain_compatibility_facades(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    calls: list[tuple[str, dict]] = []
    program_id = uuid4()
    campaign_id = uuid4()
    now = datetime.now(timezone.utc)

    async def get_campaign_activity(**kwargs):
        calls.append(("get_campaign_activity", kwargs))
        return "activity"

    async def reconcile_active_campaigns(**kwargs):
        calls.append(("reconcile_active_campaigns", kwargs))
        return 7

    async def persist_campaign_lifecycle(**kwargs):
        calls.append(("persist_campaign_lifecycle", kwargs))
        return True

    async def mark_campaign_terminal(**kwargs):
        calls.append(("mark_campaign_terminal", kwargs))
        return False

    monkeypatch.setattr(store.campaigns, "get_campaign_activity", get_campaign_activity)
    monkeypatch.setattr(store.campaigns, "reconcile_active_campaigns", reconcile_active_campaigns)
    monkeypatch.setattr(store.campaigns, "persist_campaign_lifecycle", persist_campaign_lifecycle)
    monkeypatch.setattr(store.campaigns, "mark_campaign_terminal", mark_campaign_terminal)

    assert await store.get_campaign_activity(program_id=program_id, campaign_id=campaign_id) == "activity"
    assert await store.reconcile_active_campaigns(now=now, quiet_window_seconds=30, limit=5) == 7
    assert await store._persist_campaign_lifecycle(
        campaign_id=campaign_id,
        status="running",
        active_runs=1,
        now=now,
    ) is True
    assert await store.mark_campaign_terminal(campaign_id=campaign_id, status="cancelled") is False

    assert calls == [
        ("get_campaign_activity", {"program_id": program_id, "campaign_id": campaign_id}),
        ("reconcile_active_campaigns", {"now": now, "quiet_window_seconds": 30, "limit": 5}),
        (
            "persist_campaign_lifecycle",
            {"campaign_id": campaign_id, "status": "running", "active_runs": 1, "now": now},
        ),
        ("mark_campaign_terminal", {"campaign_id": campaign_id, "status": "cancelled"}),
    ]


@pytest.mark.asyncio
async def test_record_event_remains_event_store_facade(monkeypatch) -> None:
    store = OrchestrationStore(lambda: RecordingSession())
    envelope = _envelope(_action())
    calls = []

    async def record_event(arg):
        calls.append(arg)

    monkeypatch.setattr(store.events, "record_event", record_event)
    await store.record_event(envelope)

    assert calls == [envelope]
