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
from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService

sys.modules.pop("api.infrastructure.events.event_bus", None)
sys.modules.pop("api.infrastructure.orchestration.store", None)


class StubOrchestrationStore:
    def __init__(self) -> None:
        self.policy_results: list[tuple[ActionRequest, PolicyDecision]] = []
        self.queued: list[tuple[ActionRequest, object]] = []
        self.allowed_queued: list[tuple[ActionRequest, PolicyDecision, object]] = []
        self.approved_queued: list[tuple[ActionRequest, PolicyDecision, object]] = []
        self.action_for_approval: tuple[ActionRequest | None, str | None] = (None, None)

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
        self.allowed_queued.append((action, decision, envelope))

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
    def __init__(
        self,
        *,
        capability: str = "httpx",
        profile: str = "safe-web-probe",
        safety_level: str = "safe_active",
        requires_approval: bool = False,
        scope_policy: str = "confidence",
    ) -> None:
        self.item_id = uuid4()
        self.snapshot_id = uuid4()
        self.capability = capability
        self.profile = profile
        self.safety_level = safety_level
        self.requires_approval = requires_approval
        self.scope_policy = scope_policy

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
            safety_level=self.safety_level,
            requires_approval=self.requires_approval,
            mode="routed",
            queue="analysis",
            request_event=f"{self.capability}_scan_requested",
            default_profile=self.profile,
            scope_policy=self.scope_policy,
            allowed_options=["timeout"],
        )


class StaticScopeRules:
    def __init__(self, rules: list[ScopeRuleModel]) -> None:
        self.rules = rules

    async def find_by_program(self, program_id):
        return [rule for rule in self.rules if rule.program_id == program_id]


def _service(
    store,
    bus,
    *,
    capability: str = "httpx",
    profile: str = "safe-web-probe",
    safety_level: str = "safe_active",
    requires_approval: bool = False,
    scope_policy: str = "confidence",
    scope_rules=None,
) -> ActionService:
    catalog = ActionCatalogService(
        StubCatalogStore(
            capability=capability,
            profile=profile,
            safety_level=safety_level,
            requires_approval=requires_approval,
            scope_policy=scope_policy,
        )
    )
    return ActionService(
        commands=store,
        queries=store,
        results=store,
        approvals=store,
        policy=PolicyService(),
        catalog=catalog,
        scope_rules=scope_rules,
    )


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
    assert len(store.allowed_queued) == 1
    assert bus.published == []
    _, _, envelope = store.allowed_queued[0]
    assert envelope.event == "httpx_scan_requested"
    assert envelope.event_id == submission.event_id
    assert envelope.job_id == submission.job_id
    assert envelope.run_id == submission.run_id
    assert envelope.payload["execution_budget"]["max_targets"] == 1000


@pytest.mark.asyncio
async def test_allowed_action_uses_one_atomic_store_operation() -> None:
    store = StubOrchestrationStore()
    service = _service(store, RecordingEventBus())
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
    assert len(store.allowed_queued) == 1
    queued_action, decision, envelope = store.allowed_queued[0]
    assert queued_action.action_id == action.action_id
    assert queued_action is not action
    with pytest.raises(RuntimeError, match="has not been resolved"):
        _ = action.profile
    assert decision.status is PolicyDecisionStatus.ALLOWED
    assert envelope.event_id == submission.event_id
    assert envelope.payload["scope_decision_id"] is not None
    assert store.policy_results == []
    assert store.queued == []


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



@pytest.mark.asyncio
async def test_approve_action_rechecks_scope_before_queueing_targets() -> None:
    program_id = uuid4()
    pending = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=program_id,
        catalog_id=uuid4(),
        targets=["https://api.example.com", "https://evil.test"],
        options={"timeout": 5},
    )
    scope_rules = StaticScopeRules(
        [
            ScopeRuleModel(
                program_id=program_id,
                action=ScopeAction.INCLUDE,
                rule_type=RuleType.DOMAIN,
                pattern="*.example.com",
            )
        ]
    )
    store = StubOrchestrationStore()
    store.action_for_approval = (pending, ActionStatus.REQUIRES_APPROVAL.value)
    service = _service(
        store,
        RecordingEventBus(),
        capability="ffuf",
        profile="content-discovery-light",
        safety_level="active",
        requires_approval=True,
        scope_policy="strict",
        scope_rules=scope_rules,
    )

    submission = await service.approve_action(action_id=pending.action_id, approved_by="alice")

    assert submission.status is ActionStatus.QUEUED
    _, decision, envelope = store.approved_queued[0]
    assert decision.allowed_targets == ["https://api.example.com"]
    assert decision.blocked_targets == ["https://evil.test"]
    assert envelope.targets == ["https://api.example.com"]

def test_event_dispatch_schema_is_separate_from_event_store() -> None:
    orm_source = open("src/api/infrastructure/adapters/orm_tables/dispatch_outbox.py", encoding="utf-8").read()
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


def test_action_command_and_approval_stores_record_event_and_dispatch_atomically() -> None:
    action_source = open(
        "src/api/infrastructure/orchestration/action_command_store.py",
        encoding="utf-8",
    ).read()
    approval_source = open(
        "src/api/infrastructure/orchestration/approval_store.py",
        encoding="utf-8",
    ).read()
    helper_source = open(
        "src/api/infrastructure/orchestration/action_write_helpers.py",
        encoding="utf-8",
    ).read()

    create_body = action_source.split("async def create_queued_job", 1)[1].split(
        "async def get_scope_id", 1
    )[0]
    approve_body = approval_source.split("async def approve_and_create_queued_job", 1)[1].split(
        "async def reject_action", 1
    )[0]

    assert "insert_job_run_and_dispatch(" in create_body
    assert "await session.commit()" in create_body
    assert "insert_job_run_and_dispatch(" in approve_body
    assert "await session.commit()" in approve_body
    assert "insert_event_store_row(session, envelope)" in helper_source
    assert "dispatches.enqueue_dispatch(session, envelope" in helper_source


def test_allowed_action_command_store_flow_has_one_commit_for_all_execution_state() -> None:
    action_source = open(
        "src/api/infrastructure/orchestration/action_command_store.py",
        encoding="utf-8",
    ).read()
    helper_source = open(
        "src/api/infrastructure/orchestration/action_write_helpers.py",
        encoding="utf-8",
    ).read()

    assert "async def create_allowed_action" in action_source
    body = action_source.split("async def create_allowed_action", 1)[1].split(
        "async def create_queued_job", 1
    )[0]

    assert "self.campaigns.upsert_campaign(session, action, now)" in body
    assert "self._insert_action_request(" in body
    assert "insert_policy_decision_row(" in body
    assert "record_action_detail_rows(" in body
    assert "scope_decision_id=scope_id" in body
    assert "insert_job_run_and_dispatch(" in body
    assert "insert(jobs).values(" in helper_source
    assert "insert(runs).values(" in helper_source
    assert "insert_event_store_row(session, envelope)" in helper_source
    assert "dispatches.enqueue_dispatch(session, envelope" in helper_source
    assert '"execution_budget": action.effective_budget.model_dump(mode="json")' in helper_source
    assert "run_payload=run_payload_for_action(action)" in helper_source
    assert body.count("await session.commit()") == 1
