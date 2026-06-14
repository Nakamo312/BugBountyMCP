from __future__ import annotations

from uuid import uuid4

import pytest

import sys
import types

event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")
event_bus_module.EventBus = object
store_module = types.ModuleType("api.infrastructure.orchestration.store")
store_module.OrchestrationStore = object
sys.modules.setdefault("api.infrastructure.events.event_bus", event_bus_module)
sys.modules.setdefault("api.infrastructure.orchestration.store", store_module)

dishka_module = types.ModuleType("dishka")
dishka_fastapi = types.ModuleType("dishka.integrations.fastapi")

from fastapi.routing import APIRoute

class DishkaRoute(APIRoute):  # pragma: no cover - import stub
    pass

class FromDishka:  # pragma: no cover - import stub
    def __class_getitem__(cls, item):
        return item

dishka_fastapi.DishkaRoute = DishkaRoute
dishka_fastapi.FromDishka = FromDishka
sys.modules.setdefault("dishka", dishka_module)
sys.modules.setdefault("dishka.integrations.fastapi", dishka_fastapi)


from api.application.contracts import (
    ActionKind,
    ActionRequest,
    ActionStatus,
    PolicyDecision,
)
from api.application.services.action import ActionService
from api.application.services.policy import PolicyService

sys.modules.pop("api.infrastructure.events.event_bus", None)
sys.modules.pop("api.infrastructure.orchestration.store", None)


class StubStore:
    def __init__(self) -> None:
        self.policy_results: list[tuple[ActionRequest, PolicyDecision]] = []
        self.queued: list[tuple[ActionRequest, object]] = []

    async def record_policy_result(self, action: ActionRequest, decision: PolicyDecision):
        scope_id = uuid4()
        self.policy_results.append((action, decision))
        return scope_id

    async def create_queued_job(self, action: ActionRequest, envelope) -> None:
        self.queued.append((action, envelope))


class NoopBus:
    async def publish(self, *args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("ActionService must not publish directly")



def _actions_route_module():
    import importlib.util
    from pathlib import Path

    path = Path("src/api/presentation/rest/routes/actions.py")
    spec = importlib.util.spec_from_file_location("_actions_route_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_request_action_queues_capability_from_action_contract() -> None:
    store = StubStore()
    catalog_store = StubCatalogStore(capability="httpx", profile="safe-web-probe")
    service = ActionService(
        event_bus=NoopBus(),
        store=store,
        policy=PolicyService(),
        catalog=ActionCatalogService(catalog_store),
    )
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=catalog_store.item_id,
        targets=["https://example.com"],
        options={"timeout": 10},
        requested_by="test",
    )

    submission = await service.request_action(action)

    assert submission.status is ActionStatus.QUEUED
    assert len(store.policy_results) == 1
    assert len(store.queued) == 1
    queued_action, envelope = store.queued[0]
    assert queued_action is action
    assert envelope.event == "httpx_scan_requested"
    assert envelope.payload["options"] == {"timeout": 10}
    assert envelope.payload["timeout"] == 10
    assert envelope.payload["action_id"] == str(action.action_id)
    assert envelope.profile == "safe-web-probe"


@pytest.mark.asyncio
async def test_request_action_replaces_legacy_tool_routes() -> None:
    store = StubStore()
    catalog_store = StubCatalogStore(capability="httpx", profile="safe-web-probe")
    service = ActionService(
        event_bus=NoopBus(),
        store=store,
        policy=PolicyService(),
        catalog=ActionCatalogService(catalog_store),
    )
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=catalog_store.item_id,
        targets=["https://example.com"],
        options={"timeout": 5},
        requested_by="api",
    )

    submission = await service.request_action(action)

    assert submission.status is ActionStatus.QUEUED
    queued_action, envelope = store.queued[0]
    assert queued_action is action
    assert queued_action.profile.capability_id == "httpx"
    assert queued_action.profile.profile_id == "safe-web-probe"
    assert envelope.event == "httpx_scan_requested"


def test_actions_route_exposes_canonical_create_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.post(\n    ""' in source
    assert "async def create_action(" in source
    assert "ActionRequest" in source
    assert "action_service.request_action(request)" in source


def test_frontend_uses_actions_endpoint_for_tool_runs() -> None:
    source = open("BugBountyDashBoard/src/services/api.js", encoding="utf-8").read()
    app = open("BugBountyDashBoard/src/App.jsx", encoding="utf-8").read()

    assert "api.post('/actions'" in source
    assert "catalog_id" in source
    legacy_tool_path = "api.post('/" + "sca" + "n/"
    assert legacy_tool_path not in source
    assert "/actions" in app
    legacy_page_path = "/" + "scans"
    assert legacy_page_path not in app

from api.application.action_catalog import (
    CatalogDetail,
    CatalogItem,
    CatalogItemNotFound,
    CatalogNotReady,
)
from api.application.services.action_catalog import ActionCatalogService


class StubCatalogStore:
    def __init__(
        self,
        *,
        ready: bool = True,
        missing: bool = False,
        capability: str = "katana",
        profile: str = "safe-crawl",
    ) -> None:
        self.ready = ready
        self.missing = missing
        self.item_id = uuid4()
        self.capability = capability
        self.profile = profile

    async def list_items(self):
        if not self.ready:
            raise CatalogNotReady("catalog not ready")
        return [
            CatalogItem(
                id=self.item_id,
                capability=self.capability,
                profile=self.profile,
                capability_label=self.capability,
                profile_label=self.profile,
                safety_level="safe_active",
                requires_approval=False,
                mode="routed",
            )
        ]

    async def get_detail(self, item_id):
        if not self.ready:
            raise CatalogNotReady("catalog not ready")
        if self.missing or item_id != self.item_id:
            raise CatalogItemNotFound("missing")
        return CatalogDetail(
            id=self.item_id,
            snapshot_id=uuid4(),
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
            allowed_options=["depth", "timeout"],
            frontend={},
            submit={
                "method": "POST",
                "path": "/api/v1/actions",
                "body": {
                    "catalog_id": str(self.item_id),
                    "targets": [],
                    "options": {},
                },
            },
        )


@pytest.mark.asyncio
async def test_action_catalog_service_returns_uuid_items() -> None:
    response = await ActionCatalogService(StubCatalogStore()).list_items()

    item = response[0]
    assert item.id
    assert item.capability == "katana"
    assert item.profile == "safe-crawl"
    assert item.safety_level == "safe_active"


@pytest.mark.asyncio
async def test_action_catalog_detail_returns_submit_helper() -> None:
    store = StubCatalogStore()
    item = await ActionCatalogService(store).get_detail(store.item_id)

    assert item.id == store.item_id
    assert item.allowed_options == ["depth", "timeout"]
    assert item.submit["path"] == "/api/v1/actions"
    assert item.submit["body"]["catalog_id"] == str(store.item_id)
    assert "profile" not in item.submit["body"]


@pytest.mark.asyncio
async def test_action_catalog_service_propagates_not_ready() -> None:
    with pytest.raises(CatalogNotReady):
        await ActionCatalogService(StubCatalogStore(ready=False)).list_items()


def test_actions_catalog_routes_are_registered() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.get(\n    "/catalog"' in source
    assert '@router.get(\n    "/catalog/{item_id}"' in source
    assert "CatalogNotReady" in source
    assert "status_code=503" in source
    assert "CatalogItemNotFound" in source
    assert "status_code=404" in source


def test_actions_catalog_runtime_does_not_read_yaml() -> None:
    route_source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()
    store_source = open("src/api/infrastructure/tool_catalog/store.py", encoding="utf-8").read()

    assert "load_tool_catalog_snapshot" not in route_source
    assert "load_tool_catalog_snapshot" not in store_source
    assert "tool_catalog_entries" in store_source
    assert "deactivated_at" in store_source


def test_action_and_policy_services_use_catalog_detail_not_static_capability_registry() -> None:
    action_source = open("src/api/application/services/action.py", encoding="utf-8").read()
    policy_source = open("src/api/application/services/policy.py", encoding="utf-8").read()

    assert "CAPABILITY_BY_ID" not in action_source
    assert "CAPABILITY_BY_ID" not in policy_source
    assert "CAPABILITY_BY_EVENT" not in action_source
    assert "CAPABILITY_BY_EVENT" not in policy_source
    assert "detail.request_event" in action_source
    assert "CatalogDetail" in policy_source
