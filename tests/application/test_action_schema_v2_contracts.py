from uuid import uuid4

from api.application.action_catalog import CatalogDetail
from api.application.contracts import (
    ActionKind,
    ActionRequest,
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.services.policy import PolicyService


def _request(capability: str = "httpx", profile: str = "safe-web-probe") -> ActionRequest:
    return ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10},
    ).bind_profile(capability_id=capability, profile_id=profile)


def _detail(capability: str = "httpx", profile: str = "safe-web-probe") -> CatalogDetail:
    return CatalogDetail(
        id=uuid4(),
        snapshot_id=uuid4(),
        capability=capability,
        profile=profile,
        capability_label=capability,
        profile_label=profile,
        safety_level="active" if capability == "ffuf" else "safe_active",
        requires_approval=capability == "ffuf",
        mode="routed",
        queue="analysis",
        request_event=f"{capability}_scan_requested",
        default_profile=profile,
        scope_policy="strict" if capability == "ffuf" else "confidence",
        allowed_options=["timeout"],
    )


def test_policy_decision_carries_metadata_for_durable_action_schema() -> None:
    request = _request()

    decision = PolicyService().evaluate(request, _detail())

    assert decision.metadata["capability_id"] == "httpx"
    assert decision.metadata["profile_id"] == "safe-web-probe"
    assert decision.metadata["scope_policy"]


def test_manual_approval_and_rejection_decisions_record_actor_metadata() -> None:
    request = _request("ffuf", "content-discovery-light")
    service = PolicyService()

    approved = service.approve(
        request,
        _detail("ffuf", "content-discovery-light").model_copy(
            update={"scope_policy": "confidence"}
        ),
        approved_by="alice",
        reason="ok",
    )
    rejected = service.reject(request, rejected_by="bob", reason="no")

    assert approved.metadata["approved_by"] == "alice"
    assert approved.metadata["capability_id"] == "ffuf"
    assert approved.metadata["profile_id"] == "content-discovery-light"
    assert rejected.metadata == {"rejected_by": "bob"}


def test_action_submission_surfaces_campaign_and_correlation_ids() -> None:
    decision = PolicyDecision(
        action_id=uuid4(),
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=["https://example.com"],
    )
    campaign_id = uuid4()
    correlation_id = uuid4()
    workflow_id = uuid4()

    submission = ActionSubmission(
        action_id=decision.action_id,
        status=ActionStatus.QUEUED,
        message="queued",
        campaign_id=campaign_id,
        correlation_id=correlation_id,
        workflow_id=workflow_id,
        policy_decision=decision,
    )

    assert submission.campaign_id == campaign_id
    assert submission.correlation_id == correlation_id
    assert submission.workflow_id == workflow_id
