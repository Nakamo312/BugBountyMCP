from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.application.contracts import ExecutionMode, ExecutionStatus, NodeRunClaim, NodeRunClaimRequest
from api.application.services.action import ActionService
from api.application.services.action_composition import build_action_service
from api.application.services.action_submission import ActionSubmissionWorkflow
from api.application.services.host import HostService
from api.application.services.infrastructure import InfrastructureService
from api.application.services.policy import PolicyService
from api.application.services.program import ProgramService
from api.application.pipeline.registry import NodeRegistry
from api.application.services.raw_artifact_parser import RawArtifactParserService
from api.config import Settings


ORCHESTRATION_FACADE = Path("src/api/infrastructure/orchestration/store.py")
PIPELINE_FACADE = Path("src/api/infrastructure/orchestration/pipeline_store.py")
ACTION_RUNTIME_PROVIDER = Path("src/api/infrastructure/providers/action_runtime.py")
SERVICE_PROVIDER = Path("src/api/infrastructure/providers/services.py")


def test_removed_orchestration_facade_cannot_return_as_runtime_wiring() -> None:
    assert not ORCHESTRATION_FACADE.exists()
    assert not PIPELINE_FACADE.exists()

    action_runtime = ACTION_RUNTIME_PROVIDER.read_text(encoding="utf-8")
    assert "api.infrastructure.orchestration.store" not in action_runtime
    assert "api.infrastructure.orchestration.store" not in action_runtime
    assert "def get_orchestration_store" not in action_runtime
    assert "get_orchestration_store" not in action_runtime


def test_service_constructors_accept_only_current_ports() -> None:
    service_signatures = {
        ActionService: {"reads", "feedback", "submissions", "approvals"},
        ProgramService: {"store"},
        HostService: {"host_reader", "view_reader"},
        InfrastructureService: {"reader"},
        RawArtifactParserService: {"parser"},
    }

    for service_type, expected in service_signatures.items():
        params = set(inspect.signature(service_type).parameters)
        assert params == expected

    submission_params = set(inspect.signature(ActionSubmissionWorkflow).parameters)
    assert submission_params == {
        "command_compiler",
        "policy_evaluator",
        "envelopes",
        "recorder",
        "submission_lookup",
    }


def test_action_service_is_built_only_through_explicit_composition_boundary() -> None:
    service = build_action_service(
        policy_results=object(),
        allowed_actions=object(),
        queries=object(),
        results=object(),
        approval_requests=object(),
        approval_decisions=object(),
        policy=PolicyService(),
        catalog=object(),
    )

    assert isinstance(service, ActionService)
    assert service._reads.__class__.__name__ == "ActionReadService"
    assert service._feedback.__class__.__name__ == "ActionOutcomeFeedbackService"
    assert service._submissions.__class__.__name__ == "ActionSubmissionWorkflow"
    assert service._approvals.__class__.__name__ == "ActionApprovalWorkflow"

    with pytest.raises(TypeError):
        ActionService(  # type: ignore[call-arg]
            policy_results=object(),
            allowed_actions=object(),
            queries=object(),
            results=object(),
            approval_requests=object(),
            approval_decisions=object(),
            policy=PolicyService(),
            catalog=object(),
        )


class _RunClaims:
    def __init__(self) -> None:
        self.requests: list[NodeRunClaimRequest] = []

    async def claim_node_run(self, request: NodeRunClaimRequest) -> NodeRunClaim:
        self.requests.append(request)
        return NodeRunClaim(
            run_id=uuid4(),
            claim_key=request.claim_key,
            status=ExecutionStatus.RUNNING,
            created=True,
        )


class _ScheduledLeases:
    async def count_scheduled_active_runs_by_node(self) -> dict[str, int]:
        return {"httpx": 1}

    async def lease_ready_scheduled_node_runs(self, **kwargs):
        return [SimpleNamespace(node_id="httpx", event={"event": "host.discovered"})]


class _ScheduledRecovery:
    async def recover_stale_leases(self, **kwargs) -> int:
        return 2

    async def fail_stale_scheduled_active_runs(self, **kwargs) -> int:
        return 3


class _ScheduledRetries:
    async def requeue_retryable_node_runs(self, **kwargs) -> int:
        return 4


class _RunStates:
    def __init__(self) -> None:
        self.finished: list[dict] = []

    async def mark_run_started(self, **kwargs) -> bool:
        return True

    async def mark_run_flushing(self, **kwargs) -> bool:
        return True

    async def mark_run_finished(self, **kwargs) -> bool:
        self.finished.append(kwargs)
        return True

    async def mark_run_needs_reconcile(self, **kwargs) -> None:
        return None

    async def clear_run_reconcile(self, **kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_node_registry_claim_path_uses_claim_port_request_only() -> None:
    run_claims = _RunClaims()
    registry = NodeRegistry(
        SimpleNamespace(),
        Settings(),
        node_run_claims=run_claims,
    )
    registry._nodes["httpx"] = SimpleNamespace(
        execution_mode=ExecutionMode.INLINE,
        max_expansion_depth=6,
        cooldown_seconds=300,
        token_cost=1,
    )
    event = {
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "program_id": str(uuid4()),
        "targets": ["example.com"],
    }

    claimed_event = await registry._claim_event_for_node(
        "httpx",
        "host.discovered",
        event,
    )

    assert claimed_event is not None
    assert len(run_claims.requests) == 1
    assert run_claims.requests[0].node_id == "httpx"
    assert run_claims.requests[0].event_name == "host.discovered"



@pytest.mark.asyncio
async def test_node_registry_direct_action_event_reuses_preallocated_run() -> None:
    run_claims = _RunClaims()
    registry = NodeRegistry(
        SimpleNamespace(),
        Settings(),
        node_run_claims=run_claims,
    )
    registry._nodes["ffuf"] = SimpleNamespace(
        execution_mode=ExecutionMode.INLINE,
        max_expansion_depth=6,
        cooldown_seconds=300,
        token_cost=1,
    )
    run_id = uuid4()
    event = {
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(run_id),
        "program_id": str(uuid4()),
        "targets": ["https://example.com"],
        "payload": {
            "action_invocation": {
                "schema": "action-invocation-v1",
                "action_id": str(uuid4()),
                "capability_id": "ffuf",
                "profile_id": "content-discovery-light",
            }
        },
    }

    claimed_event = await registry._claim_event_for_node(
        "ffuf",
        "ffuf_scan_requested",
        event,
    )

    assert claimed_event is not None
    assert claimed_event["run_id"] == str(run_id)
    assert run_claims.requests == []

def test_node_registry_constructor_rejects_combined_orchestration_store_path() -> None:
    with pytest.raises(TypeError):
        NodeRegistry(  # type: ignore[call-arg]
            SimpleNamespace(),
            Settings(),
            orchestration_store=object(),
        )


@pytest.mark.asyncio
async def test_scheduled_unknown_node_cancellation_uses_run_state_port() -> None:
    run_states = _RunStates()
    registry = NodeRegistry(SimpleNamespace(), Settings(), run_states=run_states)
    run_id = uuid4()

    await registry._cancel_unknown_scheduled_node_run(
        run_states=run_states,
        node_id="missing",
        run_id=run_id,
    )

    assert run_states.finished[0]["run_id"] == run_id
    assert run_states.finished[0]["status"] is ExecutionStatus.CANCELLED



def test_provider_sources_wire_current_adapters_not_legacy_constructors() -> None:
    service_provider = SERVICE_PROVIDER.read_text(encoding="utf-8")
    action_provider = ACTION_RUNTIME_PROVIDER.read_text(encoding="utf-8")

    assert "ProgramService(RepositoryProgramStore(session_factory))" in service_provider
    assert "HostService(\n            RepositoryHostAssetReader" in service_provider
    assert "AnalysisService(SQLAlchemyReadOnlyViewReader(scan_uow))" in service_provider
    assert "InfrastructureService(\n            RepositoryInfrastructureGraphReader" in service_provider
    assert "build_action_service(" in action_provider
    assert "get_node_run_claim_port" in action_provider
    assert "get_scheduled_lease_port" in action_provider
    assert "get_scheduled_recovery_port" in action_provider
    assert "get_scheduled_retry_port" in action_provider
    assert "get_scheduled_run_store_port" not in action_provider
    assert "get_pipeline_orchestration_store_port" not in action_provider
    assert "PipelineOrchestrationStore" not in action_provider
    assert "ScheduledWorkStore" not in action_provider
    assert "ActionService(" not in action_provider.replace("build_action_service(", "")
    assert "ProgramService(ProgramUnitOfWork" not in service_provider
    assert "HostService(scan_uow" not in service_provider
    assert "AnalysisService(scan_uow" not in service_provider
    assert "InfrastructureService(infrastructure_uow" not in service_provider
