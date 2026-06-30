import pytest

pytest.importorskip("sqlalchemy")

from datetime import datetime, timezone
from uuid import uuid4

from api.application.contracts import (
    ActionArtifactReference,
    ActionEventRecord,
    ActionKind,
    ActionRequest,
    ActionRunResult,
    ResolvedActionCommand,
    ActionStatus,
    EventEnvelope,
    ExecutionStatus,
    PolicyDecision,
    PolicyDecisionStatus,
    SafetyLevel,
    TerminalOutcome,
)
from api.application.execution_limits import ExecutionBudget
from api.infrastructure.adapters.orm import (
    action_request_options,
    action_request_targets,
    action_requests,
    approval_decisions,
    approval_requests,
    campaigns,
    jobs,
    policy_decisions,
    scope_decisions,
)
from api.infrastructure.orchestration.action_write_helpers import action_request_payload
from api.infrastructure.orchestration.store import OrchestrationStore


class RecordingAsyncSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False

    async def execute(self, statement):
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_action_request_schema_v2_materializes_campaign_and_correlation_fields() -> None:
    assert "workflow_id" in action_requests.c
    assert "campaign_id" in action_requests.c
    assert "correlation_id" in action_requests.c
    assert "catalog_hash" in action_requests.c
    assert "catalog_entry_id" in action_requests.c
    assert "metadata" in action_requests.c
    assert action_requests.c.campaign_id.foreign_keys

    assert "campaign_id" in jobs.c
    assert jobs.c.campaign_id.foreign_keys

    assert {"id", "program_id", "correlation_id", "workflow_id", "status"}.issubset(
        set(campaigns.c.keys())
    )


def test_action_schema_v2_has_durable_target_option_scope_and_approval_tables() -> None:
    assert {"action_id", "target", "position", "status"}.issubset(
        set(action_request_targets.c.keys())
    )
    assert {"action_id", "option_key", "option_value"}.issubset(
        set(action_request_options.c.keys())
    )
    assert {"action_id", "status", "allowed_targets", "blocked_targets"}.issubset(
        set(scope_decisions.c.keys())
    )
    assert {"action_id", "policy_decision_id", "status", "decided_at"}.issubset(
        set(approval_requests.c.keys())
    )
    assert {"approval_request_id", "action_id", "decision", "decided_by"}.issubset(
        set(approval_decisions.c.keys())
    )


def test_policy_decisions_persist_safety_metadata_and_catalog_hash() -> None:
    assert "safety_level" in policy_decisions.c
    assert "metadata" in policy_decisions.c
    assert "catalog_hash" in policy_decisions.c


def test_resolved_action_command_persists_public_request_shape_for_approval_lookup() -> None:
    request = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
    )
    command = ResolvedActionCommand.from_request(
        request,
        capability_id="httpx",
        profile_id="safe-web-probe",
        options={"timeout": 10},
        execution_budget=ExecutionBudget(
            max_duration_seconds=120,
            max_targets=100,
            rate_per_second=50,
            concurrency=20,
        ),
    )

    public_request = command.to_public_request()
    payload = action_request_payload(command)

    assert public_request.action_id == request.action_id
    assert public_request.options == {"timeout": 10}
    assert "profile" not in payload
    assert "effective_budget" not in payload
    assert ActionRequest.model_validate(payload).action_id == request.action_id


def test_orchestration_store_derives_scope_status_and_target_status() -> None:
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://a.example", "https://b.example"],
        options={"timeout": 10},
    ).bind_profile(capability_id="httpx", profile_id="safe-web-probe")
    decision = PolicyDecision(
        action_id=action.action_id,
        status=PolicyDecisionStatus.REQUIRES_APPROVAL,
        allowed_targets=["https://a.example"],
        blocked_targets=["https://b.example"],
        safety_level=SafetyLevel.ACTIVE,
        metadata={"catalog_hash": "abc123", "scope_policy": "strict"},
    )

    assert OrchestrationStore._scope_status(decision) == "partial"
    assert OrchestrationStore._target_status("https://a.example", decision) == "allowed"
    assert OrchestrationStore._target_status("https://b.example", decision) == "blocked"
    assert OrchestrationStore._target_status("https://c.example", decision) == "requested"
    assert OrchestrationStore._catalog_hash(decision) == "abc123"


@pytest.mark.asyncio
async def test_allowed_action_rolls_back_when_outbox_enqueue_fails(monkeypatch) -> None:
    session = RecordingAsyncSession()
    store = OrchestrationStore(lambda: session)
    request = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
    )
    action = ResolvedActionCommand.from_request(
        request,
        capability_id="httpx",
        profile_id="safe-web-probe",
        options={"timeout": 10},
        execution_budget=ExecutionBudget(
            max_duration_seconds=120,
            max_targets=100,
            rate_per_second=50,
            concurrency=20,
        ),
    )
    decision = PolicyDecision(
        action_id=action.action_id,
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=action.targets,
        safety_level=SafetyLevel.SAFE_ACTIVE,
        metadata={"catalog_hash": "abc123", "scope_policy": "strict"},
    )
    scope_id = uuid4()
    envelope = EventEnvelope(
        event="httpx_scan_requested",
        program_id=action.program_id,
        targets=action.targets,
        payload={"scope_decision_id": str(scope_id)},
    )

    async def fail_outbox_enqueue(*args, **kwargs) -> None:
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(store.action_commands.dispatches, "enqueue_dispatch", fail_outbox_enqueue)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await store.create_allowed_action(
            action,
            decision,
            envelope,
            scope_id=scope_id,
        )

    assert session.commits == 0
    assert session.rollbacks == 1


def test_orchestration_store_builds_action_record_from_durable_request_row() -> None:
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
        requested_by="api",
    )
    created_at = datetime.now(timezone.utc)
    updated_at = datetime.now(timezone.utc)

    record = OrchestrationStore._action_record_from_row(
        {
            "id": action.action_id,
            "program_id": action.program_id,
            "kind": action.kind.value,
            "capability_id": "httpx",
            "profile_id": "safe-web-probe",
            "requested_by": action.requested_by,
            "status": ActionStatus.QUEUED.value,
            "request": action.model_dump(mode="json"),
            "created_at": created_at,
            "updated_at": updated_at,
        }
    )

    assert record.action_id == action.action_id
    assert record.program_id == action.program_id
    assert record.targets == ["https://example.com"]
    assert record.options == {"timeout": 10}
    assert record.status is ActionStatus.QUEUED


def test_orchestration_store_builds_action_event_record_from_event_store_row() -> None:
    action_id = uuid4()
    event_id = uuid4()
    program_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    correlation_id = uuid4()
    created_at = datetime.now(timezone.utc)

    record = OrchestrationStore._action_event_record_from_row(
        {
            "event_id": event_id,
            "event_type": "httpx_scan_requested",
            "program_id": program_id,
            "job_id": job_id,
            "run_id": run_id,
            "correlation_id": correlation_id,
            "causation_id": None,
            "source": "api",
            "profile": "safe-web-probe",
            "confidence": 0.5,
            "payload": {"action_id": str(action_id), "target": "https://example.com"},
            "created_at": created_at,
        }
    )

    assert isinstance(record, ActionEventRecord)
    assert record.action_id == action_id
    assert record.event_id == event_id
    assert record.event_type == "httpx_scan_requested"
    assert record.payload["target"] == "https://example.com"

def test_orchestration_store_builds_action_run_result_from_run_row() -> None:
    run_id = uuid4()
    job_id = uuid4()
    now = datetime.now(timezone.utc)

    record = OrchestrationStore._action_run_result_from_row(
        {
            "id": run_id,
            "job_id": job_id,
            "status": ExecutionStatus.COMPLETED.value,
            "terminal_outcome": TerminalOutcome.COMPLETED.value,
            "attempt": 1,
            "error": None,
            "started_at": now,
            "finished_at": now,
        }
    )

    assert isinstance(record, ActionRunResult)
    assert record.run_id == run_id
    assert record.status is ExecutionStatus.COMPLETED
    assert record.terminal_outcome is TerminalOutcome.COMPLETED


def test_orchestration_store_builds_action_artifact_reference_from_row() -> None:
    artifact_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    created_at = datetime.now(timezone.utc)

    record = OrchestrationStore._action_artifact_reference_from_row(
        {
            "id": artifact_id,
            "job_id": job_id,
            "run_id": run_id,
            "artifact_type": "raw_tool_output",
            "storage_uri": "raw://httpx.ndjson",
            "sha256": "a" * 64,
            "size_bytes": 123,
            "storage_size_bytes": 80,
            "content_encoding": "gzip",
            "retention_class": "program_lifetime",
            "created_at": created_at,
        }
    )

    assert isinstance(record, ActionArtifactReference)
    assert record.artifact_id == artifact_id
    assert record.storage_uri == "raw://httpx.ndjson"
    assert record.storage_size_bytes == 80
    assert record.content_encoding == "gzip"
    assert record.retention_class == "program_lifetime"
    assert not hasattr(record, "body")
