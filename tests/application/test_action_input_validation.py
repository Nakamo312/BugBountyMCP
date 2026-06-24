from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionKind, ActionRequest, ActionStatus
from api.application.execution_limits import (
    ActionInputValidationError,
    ExecutionBudget,
    ExecutionBudgetRequest,
    ToolOptionSpec,
)
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.policy import PolicyService


class CatalogStore:
    def __init__(self) -> None:
        self.item_id = uuid4()

    async def get_detail(self, item_id):
        return CatalogDetail(
            id=item_id,
            snapshot_id=uuid4(),
            capability="katana",
            profile="safe-crawl",
            capability_label="Katana",
            profile_label="Safe crawl",
            safety_level="safe_active",
            mode="routed",
            queue="analysis",
            request_event="katana_scan_requested",
            default_profile="safe-crawl",
            scope_policy="none",
            option_schema={
                "depth": ToolOptionSpec(
                    type="integer",
                    default=2,
                    minimum=1,
                    maximum=5,
                ),
                "timeout": ToolOptionSpec(
                    type="integer",
                    default=60,
                    minimum=1,
                    maximum=120,
                ),
            },
            execution_budget=ExecutionBudget(
                max_duration_seconds=120,
                max_targets=2,
                rate_per_second=10,
                concurrency=2,
            ),
        )


class RecordingPolicy(PolicyService):
    def __init__(self) -> None:
        super().__init__()
        self.received_options = None

    def evaluate(self, request, detail, *, scope_rules=None):
        self.received_options = dict(request.profile.options)
        return super().evaluate(request, detail, scope_rules=scope_rules)


class RecordingStore:
    def __init__(self) -> None:
        self.allowed = []
        self.policy_results = []

    async def create_allowed_action(
        self,
        action,
        decision,
        envelope,
        *,
        scope_id,
    ) -> None:
        self.allowed.append((action, decision, envelope, scope_id))

    async def record_policy_result(self, action, decision):
        self.policy_results.append((action, decision))
        return uuid4()


class NoopBus:
    async def publish(self, *args, **kwargs):
        raise AssertionError("ActionService must persist through the outbox")


def _service():
    catalog_store = CatalogStore()
    store = RecordingStore()
    policy = RecordingPolicy()
    service = ActionService(
        event_bus=NoopBus(),
        store=store,
        policy=policy,
        catalog=ActionCatalogService(catalog_store),
        system_budget=ExecutionBudget(
            max_duration_seconds=1800,
            max_targets=1000,
            rate_per_second=1000,
            concurrency=5,
        ),
    )
    return service, store, policy, catalog_store


def _action(catalog_id, **overrides) -> ActionRequest:
    payload = {
        "kind": ActionKind.SCAN,
        "program_id": uuid4(),
        "catalog_id": catalog_id,
        "targets": ["https://example.com"],
        "options": {},
    }
    payload.update(overrides)
    return ActionRequest(**payload)


@pytest.mark.asyncio
async def test_action_service_applies_profile_defaults_before_policy() -> None:
    service, store, policy, catalog = _service()

    submission = await service.request_action(_action(catalog.item_id))

    assert submission.status is ActionStatus.QUEUED
    assert policy.received_options == {"depth": 2, "timeout": 60}
    persisted = store.allowed[0][0]
    assert persisted.options == {"depth": 2, "timeout": 60}
    assert persisted.metadata["effective_budget"]["max_targets"] == 2


@pytest.mark.asyncio
async def test_invalid_option_type_creates_no_policy_record_or_job() -> None:
    service, store, policy, catalog = _service()

    with pytest.raises(ActionInputValidationError, match="depth must be integer"):
        await service.request_action(
            _action(catalog.item_id, options={"depth": "3"})
        )

    assert policy.received_options is None
    assert store.policy_results == []
    assert store.allowed == []


@pytest.mark.asyncio
async def test_action_cannot_expand_profile_budget() -> None:
    service, store, policy, catalog = _service()

    with pytest.raises(ActionInputValidationError, match="max_targets exceeds"):
        await service.request_action(
            _action(
                catalog.item_id,
                budget=ExecutionBudgetRequest(max_targets=3),
            )
        )

    assert policy.received_options is None
    assert store.allowed == []


@pytest.mark.asyncio
async def test_action_target_count_cannot_exceed_effective_budget() -> None:
    service, store, policy, catalog = _service()

    with pytest.raises(ActionInputValidationError, match="target count 3 exceeds"):
        await service.request_action(
            _action(
                catalog.item_id,
                targets=[
                    "https://a.example.com",
                    "https://b.example.com",
                    "https://c.example.com",
                ],
            )
        )

    assert policy.received_options is None
    assert store.allowed == []


def test_action_route_maps_input_validation_to_422() -> None:
    source = open(
        "src/api/presentation/rest/routes/actions.py",
        encoding="utf-8",
    ).read()

    assert "ActionInputValidationError" in source
    assert "except ActionInputValidationError as exc" in source
    assert "status_code=422" in source
