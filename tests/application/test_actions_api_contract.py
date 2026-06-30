from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

import sys
import types

try:
    from api.infrastructure.events.event_bus import EventBus  # noqa: F401
except ImportError:
    event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")
    event_bus_module.EventBus = object
    sys.modules.setdefault("api.infrastructure.events.event_bus", event_bus_module)

try:
    from api.infrastructure.orchestration.store import OrchestrationStore  # noqa: F401
except ImportError:
    store_module = types.ModuleType("api.infrastructure.orchestration.store")
    store_module.OrchestrationStore = object
    sys.modules.setdefault("api.infrastructure.orchestration.store", store_module)

try:
    from dishka.integrations.fastapi import DishkaRoute, FromDishka  # noqa: F401
except ImportError:
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
    ActionArtifactReference,
    ActionEventRecord,
    ActionKind,
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionOutcomeMeasures,
    ActionOutcomeRecord,
    ActionOutcomeScore,
    ActionRecord,
    ActionRequest,
    ActionResultRecord,
    ActionRunResult,
    ActionStatus,
    ExecutionStatus,
    PolicyDecision,
    TerminalOutcome,
)
from api.application.services.action import ActionNotFoundError, ActionService
from api.application.services.policy import PolicyService
from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel

sys.modules.pop("api.infrastructure.events.event_bus", None)
sys.modules.pop("api.infrastructure.orchestration.store", None)


class StubStore:
    def __init__(self) -> None:
        self.policy_results: list[tuple[ActionRequest, PolicyDecision]] = []
        self.queued: list[tuple[ActionRequest, object]] = []
        self.actions_by_id = {}
        self.events_by_action_id = {}
        self.runs_by_action_id = {}
        self.artifacts_by_action_id = {}

    async def record_policy_result(self, action: ActionRequest, decision: PolicyDecision):
        scope_id = uuid4()
        self.policy_results.append((action, decision))
        return scope_id

    async def create_queued_job(self, action: ActionRequest, envelope) -> None:
        self.queued.append((action, envelope))

    async def create_allowed_action(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
        envelope,
        *,
        scope_id,
    ) -> None:
        self.policy_results.append((action, decision))
        self.queued.append((action, envelope))

    async def get_action(self, action_id):
        return self.actions_by_id.get(action_id)

    async def list_action_events(self, action_id, *, limit: int = 100, offset: int = 0):
        return list(self.events_by_action_id.get(action_id, []))[offset : offset + limit]

    async def list_action_runs(self, action_id):
        return list(self.runs_by_action_id.get(action_id, []))

    async def list_action_artifacts(self, action_id):
        return list(self.artifacts_by_action_id.get(action_id, []))


class NoopBus:
    async def publish(self, *args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("ActionService must not publish directly")


class RecordingScopeRules:
    def __init__(self, rules):
        self.rules = list(rules)
        self.program_ids = []

    async def find_by_program(self, program_id):
        self.program_ids.append(program_id)
        return list(self.rules)


class RecordingOutcomeFeedbackWriter:
    def __init__(self, record: ActionOutcomeFeedbackRecord | None = None) -> None:
        self.record = record
        self.calls = []

    async def apply_feedback(self, *, action_id, feedback):
        self.calls.append((action_id, feedback))
        return self.record


def _feedback_record(*, action_id, program_id, now) -> ActionOutcomeFeedbackRecord:
    outcome_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    outcome = ActionOutcomeRecord(
        outcome_id=outcome_id,
        program_id=program_id,
        action_id=action_id,
        job_id=job_id,
        run_id=run_id,
        capability_id="httpx",
        profile_id="safe-web-probe",
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
        attempt=1,
        measures=ActionOutcomeMeasures(),
        score=ActionOutcomeScore(
            information_gain_score=1.0,
            score_version="test",
            score_breakdown={},
        ),
        created_at=now,
        updated_at=now,
    )
    return ActionOutcomeFeedbackRecord(
        feedback_id=uuid4(),
        outcome_id=outcome_id,
        program_id=program_id,
        action_id=action_id,
        job_id=job_id,
        run_id=run_id,
        manual_interest=True,
        actor="human",
        source="api",
        reason="useful branch",
        confidence=0.8,
        created_at=now,
        outcome=outcome,
    )


class RecordingPolicy(PolicyService):
    def __init__(self):
        super().__init__()
        self.received_scope_rules = None

    def evaluate(self, request, detail, *, scope_rules=None):
        self.received_scope_rules = list(scope_rules or [])
        return super().evaluate(request, detail, scope_rules=scope_rules)


def _action_service(
    store,
    *,
    policy=None,
    catalog_store=None,
    scope_rules=None,
    outcome_feedback=None,
) -> ActionService:
    return ActionService(
        commands=store,
        queries=store,
        results=store,
        approvals=store,
        policy=policy or PolicyService(),
        catalog=ActionCatalogService(catalog_store or StubCatalogStore()),
        scope_rules=scope_rules,
        outcome_feedback=outcome_feedback,
    )



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
    service = _action_service(store, catalog_store=catalog_store)
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
    assert queued_action.action_id == action.action_id
    assert queued_action is not action
    with pytest.raises(RuntimeError, match="has not been resolved"):
        _ = action.profile
    assert envelope.event == "httpx_scan_requested"
    assert envelope.payload["options"] == {"timeout": 10}
    assert envelope.payload["options"]["timeout"] == 10
    assert envelope.payload["action_id"] == str(action.action_id)
    assert envelope.payload["campaign_id"] == str(action.campaign_id)
    assert envelope.campaign_id == action.campaign_id
    assert envelope.expansion_depth == 0
    assert envelope.correlation_id == action.correlation_id
    assert envelope.profile == "safe-web-probe"


@pytest.mark.asyncio
async def test_request_action_replaces_legacy_tool_routes() -> None:
    store = StubStore()
    catalog_store = StubCatalogStore(capability="httpx", profile="safe-web-probe")
    service = _action_service(store, catalog_store=catalog_store)
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
    assert queued_action.action_id == action.action_id
    assert queued_action is not action
    assert queued_action.profile.capability_id == "httpx"
    assert queued_action.profile.profile_id == "safe-web-probe"
    assert envelope.event == "httpx_scan_requested"


@pytest.mark.asyncio
async def test_request_action_loads_program_scope_rules_before_policy_evaluation() -> None:
    program_id = uuid4()
    rule = ScopeRuleModel(
        program_id=program_id,
        action=ScopeAction.INCLUDE,
        rule_type=RuleType.DOMAIN,
        pattern="*.example.com",
    )
    scope_rules = RecordingScopeRules([rule])
    policy = RecordingPolicy()
    store = StubStore()
    catalog_store = StubCatalogStore(
        capability="ffuf",
        profile="content-discovery-light",
        scope_policy="strict",
        safety_level="active",
        requires_approval=True,
    )
    service = _action_service(
        store,
        policy=policy,
        catalog_store=catalog_store,
        scope_rules=scope_rules,
    )
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=program_id,
        catalog_id=catalog_store.item_id,
        targets=["https://api.example.com"],
        options={"timeout": 10},
        requested_by="test",
    )

    submission = await service.request_action(action)

    assert submission.status is ActionStatus.REQUIRES_APPROVAL
    assert scope_rules.program_ids == [program_id]
    assert policy.received_scope_rules == [rule]


@pytest.mark.asyncio
async def test_get_action_returns_stored_action_record_by_id() -> None:
    action_id = uuid4()
    record = ActionRecord(
        action_id=action_id,
        program_id=uuid4(),
        kind=ActionKind.SCAN,
        capability_id="httpx",
        profile_id="safe-web-probe",
        requested_by="api",
        status=ActionStatus.QUEUED,
        targets=["https://example.com"],
        options={"timeout": 10},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    store = StubStore()
    store.actions_by_id[action_id] = record
    service = _action_service(store)

    assert await service.get_action(action_id) == record

    with pytest.raises(ActionNotFoundError):
        await service.get_action(uuid4())


@pytest.mark.asyncio
async def test_list_action_events_returns_stored_events_for_action() -> None:
    action_id = uuid4()
    event = ActionEventRecord(
        event_id=uuid4(),
        action_id=action_id,
        event_type="httpx_scan_requested",
        program_id=uuid4(),
        job_id=uuid4(),
        run_id=uuid4(),
        correlation_id=uuid4(),
        source="api",
        profile="safe-web-probe",
        confidence=0.5,
        payload={"action_id": str(action_id), "target": "https://example.com"},
        created_at=datetime.now(timezone.utc),
    )
    store = StubStore()
    store.actions_by_id[action_id] = ActionRecord(
        action_id=action_id,
        program_id=event.program_id,
        kind=ActionKind.SCAN,
        capability_id="httpx",
        profile_id="safe-web-probe",
        requested_by="api",
        status=ActionStatus.QUEUED,
        targets=["https://example.com"],
        options={},
        created_at=event.created_at,
        updated_at=event.created_at,
    )
    store.events_by_action_id[action_id] = [event]
    service = _action_service(store)

    assert await service.list_action_events(action_id, limit=10, offset=0) == [event]


@pytest.mark.asyncio
async def test_get_action_result_returns_terminal_runs_and_artifact_references() -> None:
    action_id = uuid4()
    program_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    now = datetime.now(timezone.utc)
    action = ActionRecord(
        action_id=action_id,
        program_id=program_id,
        kind=ActionKind.SCAN,
        capability_id="httpx",
        profile_id="safe-web-probe",
        requested_by="api",
        status=ActionStatus.QUEUED,
        targets=["https://example.com"],
        options={},
        created_at=now,
        updated_at=now,
    )
    run = ActionRunResult(
        run_id=run_id,
        job_id=job_id,
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
        attempt=1,
        started_at=now,
        finished_at=now,
    )
    artifact = ActionArtifactReference(
        artifact_id=uuid4(),
        job_id=job_id,
        run_id=run_id,
        artifact_type="raw_tool_output",
        storage_uri="raw://httpx.ndjson",
        sha256="a" * 64,
        size_bytes=123,
        created_at=now,
    )
    store = StubStore()
    store.actions_by_id[action_id] = action
    store.runs_by_action_id[action_id] = [run]
    store.artifacts_by_action_id[action_id] = [artifact]
    service = _action_service(store)

    result = await service.get_action_result(action_id)

    assert isinstance(result, ActionResultRecord)
    assert result.action_id == action_id
    assert result.ready is True
    assert result.runs == [run]
    assert result.artifacts == [artifact]


@pytest.mark.asyncio
async def test_record_outcome_feedback_goes_through_action_service_boundary() -> None:
    action_id = uuid4()
    program_id = uuid4()
    now = datetime.now(timezone.utc)
    store = StubStore()
    store.actions_by_id[action_id] = ActionRecord(
        action_id=action_id,
        program_id=program_id,
        kind=ActionKind.SCAN,
        capability_id="httpx",
        profile_id="safe-web-probe",
        requested_by="api",
        status=ActionStatus.QUEUED,
        targets=["https://example.com"],
        options={},
        created_at=now,
        updated_at=now,
    )
    writer = RecordingOutcomeFeedbackWriter(
        _feedback_record(action_id=action_id, program_id=program_id, now=now)
    )
    service = _action_service(store, outcome_feedback=writer)
    request = ActionOutcomeFeedback(
        manual_interest=True,
        actor="human",
        source="ui",
        reason="continue this branch",
        confidence=0.8,
    )

    record = await service.record_outcome_feedback(action_id=action_id, feedback=request)

    assert record.action_id == action_id
    assert writer.calls == [(action_id, request)]


def test_actions_route_exposes_canonical_create_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.post(\n    ""' in source
    assert "async def create_action(" in source
    assert "ActionRequest" in source
    assert "action_service.request_action(request)" in source


def test_tool_actions_route_alias_is_registered_for_public_mvp_contract() -> None:
    source = open("src/api/presentation/rest/routes/__init__.py", encoding="utf-8").read()

    assert 'router.include_router(actions_router, prefix="/api/v1/actions"' in source
    assert 'router.include_router(actions_router, prefix="/api/v1/tool-actions"' in source


def test_actions_route_exposes_get_action_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.get(\n    "/{action_id}"' in source
    assert "async def get_action(" in source
    assert "action_service.get_action(action_id)" in source
    assert "ActionNotFoundError" in source
    assert "status_code=404" in source


def test_actions_route_exposes_action_events_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.get(\n    "/{action_id}/events"' in source
    assert "async def list_action_events(" in source
    assert "action_service.list_action_events(" in source
    assert '"items": [event.model_dump(mode="json") for event in events]' in source


def test_actions_route_exposes_action_result_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.get(\n    "/{action_id}/result"' in source
    assert "async def get_action_result(" in source
    assert "action_service.get_action_result(action_id)" in source
    assert 'result.model_dump(mode="json")' in source



def test_actions_route_exposes_action_outcome_feedback_endpoint() -> None:
    source = open("src/api/presentation/rest/routes/actions.py", encoding="utf-8").read()

    assert '@router.post(\n    "/{action_id}/outcome-feedback"' in source
    assert "async def record_action_outcome_feedback(" in source
    assert "ActionOutcomeFeedback" in source
    assert "action_service.record_outcome_feedback(" in source
    assert "ActionOutcomeFeedbackUnavailable" in source
    assert "status_code=404" in source

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
        safety_level: str = "safe_active",
        requires_approval: bool = False,
        scope_policy: str = "confidence",
    ) -> None:
        self.ready = ready
        self.missing = missing
        self.item_id = uuid4()
        self.capability = capability
        self.profile = profile
        self.safety_level = safety_level
        self.requires_approval = requires_approval
        self.scope_policy = scope_policy

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
                safety_level=self.safety_level,
                requires_approval=self.requires_approval,
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
            safety_level=self.safety_level,
            requires_approval=self.requires_approval,
            mode="routed",
            queue="analysis",
            request_event=f"{self.capability}_scan_requested",
            default_profile=self.profile,
            scope_policy=self.scope_policy,
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
    action_source = (
        open("src/api/application/services/action.py", encoding="utf-8").read()
        + open("src/api/application/services/action_submission.py", encoding="utf-8").read()
    )
    policy_source = open("src/api/application/services/policy.py", encoding="utf-8").read()

    assert "CAPABILITY_BY_ID" not in action_source
    assert "CAPABILITY_BY_ID" not in policy_source
    assert "CAPABILITY_BY_EVENT" not in action_source
    assert "CAPABILITY_BY_EVENT" not in policy_source
    assert "detail.request_event" in action_source
    assert "CatalogDetail" in policy_source
