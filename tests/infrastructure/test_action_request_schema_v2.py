import pytest

pytest.importorskip("sqlalchemy")

from uuid import uuid4

from api.application.contracts import (
    ActionKind,
    ActionRequest,
    PolicyDecision,
    PolicyDecisionStatus,
    SafetyLevel,
)
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
from api.infrastructure.orchestration.store import OrchestrationStore


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
