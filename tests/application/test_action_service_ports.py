from __future__ import annotations

from api.application.action_invocation_payload import action_invocation_mapping
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
)
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService
from tests.application.test_actions_api_contract import StubCatalogStore


class SplitCommandPort:
    def __init__(self) -> None:
        self.created = []
        self.recorded = []

    async def record_policy_result(self, action, decision):
        self.recorded.append((action, decision))
        return uuid4()

    async def create_allowed_action(self, action, decision, envelope, *, scope_id):
        self.created.append((action, decision, envelope, scope_id))


class SplitQueryPort:
    def __init__(self) -> None:
        self.actions = {}
        self.get_calls = []

    async def list_actions(self, *, status=None, program_id=None, limit=100, offset=0):
        return list(self.actions.values())[offset : offset + limit]

    async def get_action(self, action_id):
        self.get_calls.append(action_id)
        return self.actions.get(action_id)

    async def list_action_events(self, action_id, *, limit=100, offset=0):
        return []


class SplitResultPort:
    def __init__(self) -> None:
        self.runs = {}
        self.artifacts = {}
        self.run_calls = []

    async def list_action_runs(self, action_id):
        self.run_calls.append(action_id)
        return list(self.runs.get(action_id, []))

    async def list_action_artifacts(self, action_id):
        return list(self.artifacts.get(action_id, []))


class SplitApprovalPort:
    def __init__(self, action=None) -> None:
        self.action = action
        self.approved = []

    async def get_action_for_approval(self, action_id):
        return self.action, ActionStatus.REQUIRES_APPROVAL.value

    async def get_scope_id(self, action_id):
        return uuid4()

    async def approve_and_create_queued_job(self, action, decision, envelope):
        self.approved.append((action, decision, envelope))
        return True

    async def reject_action(self, action, decision):
        return True


def test_action_service_rejects_legacy_store_composite_port() -> None:
    with pytest.raises(TypeError, match="explicit command, query, result, and approval ports"):
        ActionService(
            store=object(),
            policy=PolicyService(),
            catalog=ActionCatalogService(StubCatalogStore()),
        )


@pytest.mark.asyncio
async def test_action_service_accepts_separate_narrow_ports() -> None:
    catalog_store = StubCatalogStore(capability="httpx", profile="safe-web-probe")
    request = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=catalog_store.item_id,
        targets=["https://example.com"],
        options={"timeout": 10},
        requested_by="test",
    )
    commands = SplitCommandPort()
    queries = SplitQueryPort()
    results = SplitResultPort()
    approvals = SplitApprovalPort(action=request)
    service = ActionService(
        commands=commands,
        queries=queries,
        results=results,
        approvals=approvals,
        policy=PolicyService(),
        catalog=ActionCatalogService(catalog_store),
    )

    submission = await service.request_action(request)

    assert submission.status is ActionStatus.QUEUED
    assert len(commands.created) == 1
    queued_action, _, envelope, _ = commands.created[0]
    assert queued_action.action_id == request.action_id
    assert queued_action is not request
    assert queued_action.profile.profile_id == "safe-web-probe"
    with pytest.raises(RuntimeError, match="has not been resolved"):
        _ = request.profile
    invocation_payload = action_invocation_mapping(envelope.payload)

    assert invocation_payload["options"]["timeout"] == 10
    assert "options" not in envelope.payload

    now = datetime.now(timezone.utc)
    queries.actions[request.action_id] = ActionRecord(
        action_id=request.action_id,
        program_id=request.program_id,
        kind=ActionKind.SCAN,
        capability_id="httpx",
        profile_id="safe-web-probe",
        requested_by="test",
        status=ActionStatus.QUEUED,
        targets=["https://example.com"],
        options={"timeout": 10},
        created_at=now,
        updated_at=now,
    )
    result = await service.get_action_result(request.action_id)

    assert result.action_id == request.action_id
    assert results.run_calls == [request.action_id]

    approval_submission = await service.approve_action(action_id=request.action_id)

    assert approval_submission.status is ActionStatus.QUEUED
    assert len(approvals.approved) == 1
