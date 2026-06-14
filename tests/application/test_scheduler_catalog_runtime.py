from __future__ import annotations

from uuid import UUID, uuid4

import sys
import types

import pytest

event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")
event_bus_module.EventBus = object
store_module = types.ModuleType("api.infrastructure.orchestration.store")
store_module.OrchestrationStore = object
sys.modules.setdefault("api.infrastructure.events.event_bus", event_bus_module)
sys.modules.setdefault("api.infrastructure.orchestration.store", store_module)

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionKind, ActionRequest, ActionStatus, ActionSubmission
from api.application.scheduler import ActionScheduler, ScheduledActionSpec
from api.application.services.action_catalog import ActionCatalogService

sys.modules.pop("api.infrastructure.events.event_bus", None)
sys.modules.pop("api.infrastructure.orchestration.store", None)


def _detail(item_id: UUID, *, event: str = "custom_catalog_event_requested") -> CatalogDetail:
    return CatalogDetail(
        id=item_id,
        snapshot_id=uuid4(),
        capability="custom-tool",
        profile="default",
        capability_label="Custom tool",
        profile_label="Default",
        safety_level="safe_active",
        requires_approval=False,
        mode="routed",
        queue="analysis",
        request_event=event,
        default_profile="default",
        scope_policy="confidence",
        allowed_options=["depth"],
        frontend={},
        submit={
            "method": "POST",
            "path": "/api/v1/actions",
            "body": {"catalog_id": str(item_id), "targets": [], "options": {}},
        },
    )


class EventCatalogStore:
    def __init__(self) -> None:
        self.item_id = uuid4()
        self.event_lookups: list[tuple[str, str | None]] = []
        self.capability_lookups: list[tuple[str, str]] = []

    async def list_items(self):  # pragma: no cover - not used here
        raise AssertionError("scheduler should not list catalog items")

    async def get_detail(self, item_id):  # pragma: no cover - not used here
        raise AssertionError("scheduler should not fetch catalog items by id")

    async def find_detail(self, *, capability: str, profile: str):
        self.capability_lookups.append((capability, profile))
        raise AssertionError("scheduler must not resolve scheduled work through capability/profile")

    async def find_detail_by_event(self, *, event: str, profile: str | None = None):
        self.event_lookups.append((event, profile))
        return _detail(self.item_id, event=event)


class RecordingActionService:
    def __init__(self) -> None:
        self.requests: list[ActionRequest] = []

    async def request_action(self, action: ActionRequest, *, confidence: float = 0.5):
        self.requests.append(action)
        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message="queued",
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
        )


def test_scheduled_action_event_is_not_validated_against_static_registry() -> None:
    spec = ScheduledActionSpec(
        enabled=True,
        interval="5m",
        event="custom_catalog_event_requested",
        program_id=uuid4(),
        targets=["https://example.com"],
    )

    assert spec.event == "custom_catalog_event_requested"
    assert spec.interval == 300


@pytest.mark.asyncio
async def test_action_catalog_service_can_resolve_active_entry_by_request_event() -> None:
    store = EventCatalogStore()
    service = ActionCatalogService(store)

    detail = await service.find_detail_by_event(
        event="custom_catalog_event_requested",
        profile=None,
    )

    assert detail.id == store.item_id
    assert store.event_lookups == [("custom_catalog_event_requested", None)]
    assert store.capability_lookups == []


@pytest.mark.asyncio
async def test_scheduler_submits_catalog_id_resolved_from_event_not_static_capability() -> None:
    store = EventCatalogStore()
    action_service = RecordingActionService()
    scheduler = ActionScheduler(
        action_service=action_service,
        catalog_service=ActionCatalogService(store),
        config=None,  # _submit does not read scheduler config
    )
    spec = ScheduledActionSpec.model_construct(
        enabled=True,
        interval=1,
        run_on_start=True,
        event="custom_catalog_event_requested",
        program_id=uuid4(),
        targets=["https://example.com"],
        profile_id=None,
        options={"depth": 1},
        requested_by="scheduler",
        confidence=0.8,
    )

    await scheduler._submit("custom", spec)

    assert store.event_lookups == [("custom_catalog_event_requested", None)]
    assert store.capability_lookups == []
    assert len(action_service.requests) == 1
    request = action_service.requests[0]
    assert request.kind is ActionKind.SCAN
    assert request.catalog_id == store.item_id
    assert request.targets == ["https://example.com"]
    assert request.options == {"depth": 1}
    assert request.requested_by == "scheduler"


def test_scheduler_runtime_has_no_static_capability_event_registry_dependency() -> None:
    source = open("src/api/application/scheduler.py", encoding="utf-8").read()

    assert "CAPABILITY_BY_EVENT" not in source
