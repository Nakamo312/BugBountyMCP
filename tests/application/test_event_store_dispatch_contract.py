from __future__ import annotations

from uuid import uuid4
import sys
import types

import pytest

# Keep these application tests independent from live infrastructure packages that
# are not installed in the sandbox. ActionService only needs these imports for
# type boundaries in this test module.
event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")
event_bus_module.EventBus = object
store_module = types.ModuleType("api.infrastructure.orchestration.store")
store_module.OrchestrationStore = object
sys.modules.setdefault("api.infrastructure.events.event_bus", event_bus_module)
sys.modules.setdefault("api.infrastructure.orchestration.store", store_module)

from api.application.contracts import (
    ActionKind,
    ActionRequest,
    ActionStatus,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.action_catalog import CatalogDetail
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService

sys.modules.pop("api.infrastructure.events.event_bus", None)
sys.modules.pop("api.infrastructure.orchestration.store", None)


class StubOrchestrationStore:
    def __init__(self) -> None:
        self.policy_results: list[tuple[ActionRequest, PolicyDecision]] = []
        self.queued: list[tuple[ActionRequest, object]] = []
        self.approved_queued: list[tuple[ActionRequest, PolicyDecision, object]] = []
        self.action_for_approval: tuple[ActionRequest | None, str | None] = (None, None)

    async def record_policy_result(self, action: ActionRequest, decision: PolicyDecision):
        scope_id = uuid4()
        self.policy_results.append((action, decision))
        return scope_id

    async def create_queued_job(self, action: ActionRequest, envelope) -> None:
        self.queued.append((action, envelope))

    async def get_action_for_approval(self, action_id):
        return self.action_for_approval

    async def get_scope_id(self, action_id):
        return uuid4()

    async def approve_and_create_queued_job(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
        envelope,
    ) -> bool:
        self.approved_queued.append((action, decision, envelope))
        return True


class RecordingEventBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, envelope) -> None:
        self.published.append(envelope)
        raise AssertionError("ActionService must not publish queued actions directly")


class StubCatalogStore:
    def __init__(self, *, capability: str = "httpx", profile: str = "safe-web-probe") -> None:
        self.item_id = uuid4()
        self.snapshot_id = uuid4()
        self.capability = capability
        self.profile = profile

    async def list_items(self):
        return []

    async def get_detail(self, item_id):
        return CatalogDetail(
            id=item_id,
            snapshot_id=self.snapshot_id,
            capability=self.capability,
            profile=self.profile,
            capability_label=self.capability,
            profile_label=self.profile,
            safety_level="safe_active",
            requires_approval=False,
            mode="routed",
            queue="analysis",
            request_event=f"{self.capability}_scan_requested",
            default_profile=self.profile,
            scope_policy="confidence",
            allowed_options=["timeout"],
        )


def _service(store, bus, *, capability: str = "httpx", profile: str = "safe-web-probe") -> ActionService:
    catalog = ActionCatalogService(StubCatalogStore(capability=capability, profile=profile))
    return ActionService(event_bus=bus, store=store, policy=PolicyService(), catalog=catalog)


@pytest.mark.asyncio
async def test_request_action_persists_event_for_dispatch_without_direct_publish() -> None:
    store = StubOrchestrationStore()
    bus = RecordingEventBus()
    service = _service(store, bus)
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
        requested_by="api",
    )

    submission = await service.request_action(action)

    assert submission.status is ActionStatus.QUEUED
    assert len(store.policy_results) == 1
    assert len(store.queued) == 1
    assert bus.published == []
    _, envelope = store.queued[0]
    assert envelope.event == "httpx_scan_requested"
    assert envelope.event_id == submission.event_id
    assert envelope.job_id == submission.job_id
    assert envelope.run_id == submission.run_id


@pytest.mark.asyncio
async def test_approve_action_persists_event_for_dispatch_without_direct_publish() -> None:
    pending = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 5},
    )
    store = StubOrchestrationStore()
    store.action_for_approval = (pending, ActionStatus.REQUIRES_APPROVAL.value)
    bus = RecordingEventBus()
    service = _service(store, bus, capability="ffuf", profile="content-discovery-light")

    submission = await service.approve_action(action_id=pending.action_id, approved_by="alice")

    assert submission.status is ActionStatus.QUEUED
    assert len(store.approved_queued) == 1
    assert bus.published == []
    _, decision, envelope = store.approved_queued[0]
    assert decision.status is PolicyDecisionStatus.ALLOWED
    assert envelope.event == "ffuf_scan_requested"
    assert envelope.event_id == submission.event_id


def test_event_dispatch_schema_is_separate_from_event_store() -> None:
    orm_source = open("src/api/infrastructure/adapters/orm.py", encoding="utf-8").read()
    migration_source = open(
        "alembic/versions/x4y5z6a7b8c9_event_store_dispatches.py",
        encoding="utf-8",
    ).read()

    assert "event_store = Table(" in orm_source
    assert "event_dispatches = Table(" in orm_source
    assert "event_store.event_id" in orm_source
    assert "destination" in orm_source
    assert "routing_key" in orm_source
    assert "event_dispatches" in migration_source
    assert "uq_event_dispatches_event_destination" in migration_source


def test_orchestration_store_records_event_and_dispatch_in_same_queued_job_flow() -> None:
    source = open("src/api/infrastructure/orchestration/store.py", encoding="utf-8").read()
    create_body = source.split("async def create_queued_job", 1)[1].split(
        "async def approve_and_create_queued_job", 1
    )[0]
    approve_body = source.split("async def approve_and_create_queued_job", 1)[1].split(
        "async def mark_run_started", 1
    )[0]

    assert "_insert_event_store_row(session, envelope)" in create_body
    assert "_enqueue_dispatch(session, envelope" in create_body
    assert "await session.commit()" in create_body
    assert "_insert_event_store_row(session, envelope)" in approve_body
    assert "_enqueue_dispatch(session, envelope" in approve_body
    assert "await session.commit()" in approve_body
