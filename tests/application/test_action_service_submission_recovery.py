from __future__ import annotations

import importlib
import sys
import types
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from api.application.contracts import ActionKind, ActionRecord, ActionStatus, PolicyDecisionStatus
from api.application.services.action_read import policy_decision_status_for_action_status


class _Store:
    def __init__(self, action: ActionRecord | None) -> None:
        self.action = action

    async def get_action(self, action_id):
        return self.action


class _ResultPort:
    async def list_action_runs(self, action_id):
        return []

    async def list_action_artifacts(self, action_id):
        return []


class _UnusedPort:
    pass


@pytest.mark.asyncio
async def test_action_service_get_action_submission_builds_recovery_submission(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "aio_pika",
        types.SimpleNamespace(
            RobustConnection=object,
            Channel=object,
            ExchangeType=types.SimpleNamespace(TOPIC="topic", DIRECT="direct"),
            DeliveryMode=types.SimpleNamespace(PERSISTENT=2),
            Message=lambda **kwargs: kwargs,
            connect_robust=None,
        ),
    )
    action_module = importlib.import_module("api.application.services.action")
    action_id = uuid4()
    action = ActionRecord(
        action_id=action_id,
        program_id=uuid4(),
        kind=ActionKind.SCAN,
        capability_id="http",
        profile_id="probe",
        requested_by="reviewer",
        status=ActionStatus.QUEUED,
        targets=["https://example.test"],
        options={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    service = action_module.ActionService(
        commands=_UnusedPort(),
        queries=_Store(action),
        results=_ResultPort(),
        approvals=_UnusedPort(),
        policy=object(),
        catalog=object(),
    )

    submission = await service.get_action_submission(action_id)

    assert submission is not None
    assert submission.action_id == action_id
    assert submission.status is ActionStatus.QUEUED
    assert submission.policy_decision.status is PolicyDecisionStatus.ALLOWED
    assert submission.correlation_id is None
    assert submission.workflow_id is None


def test_policy_decision_recovery_rejects_unknown_action_status() -> None:
    with pytest.raises(ValueError, match="unsupported action status"):
        policy_decision_status_for_action_status(object())  # type: ignore[arg-type]


class _WriteOnlyStore:
    pass


@pytest.mark.asyncio
async def test_action_service_get_action_submission_is_optional_for_write_only_stores(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "aio_pika",
        types.SimpleNamespace(
            RobustConnection=object,
            Channel=object,
            ExchangeType=types.SimpleNamespace(TOPIC="topic", DIRECT="direct"),
            DeliveryMode=types.SimpleNamespace(PERSISTENT=2),
            Message=lambda **kwargs: kwargs,
            connect_robust=None,
        ),
    )
    action_module = importlib.import_module("api.application.services.action")
    service = action_module.ActionService(
        commands=_UnusedPort(),
        queries=_WriteOnlyStore(),
        results=_ResultPort(),
        approvals=_UnusedPort(),
        policy=object(),
        catalog=object(),
    )

    assert await service.get_action_submission(uuid4()) is None
