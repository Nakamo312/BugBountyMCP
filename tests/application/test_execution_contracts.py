from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.application.contracts import (
    ActionKind,
    ActionRequest,
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
    SafetyLevel,
    ToolInvocation,
)
from api.application.execution_limits import ExecutionBudget
from api.application.pipeline.invocation import build_invocation
from api.application.services.action_envelope import ActionEnvelopeBuilder


def test_existing_action_request_is_the_tool_action_request_contract() -> None:
    catalog_id = uuid4()
    request = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=catalog_id,
        targets=["https://example.com"],
        options={"timeout": 30, "follow_redirects": False},
        requested_by="langgraph",
        workflow_id=uuid4(),
        metadata={"objective": "probe web roots"},
    )

    assert request.catalog_id == catalog_id
    assert request.targets == ["https://example.com"]
    assert request.options == {"timeout": 30, "follow_redirects": False}
    assert request.requested_by == "langgraph"
    assert request.campaign_id is not None
    assert request.correlation_id is not None


def test_action_request_rejects_legacy_profile_payload() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(
            kind=ActionKind.SCAN,
            program_id=uuid4(),
            profile={
                "capability_id": "httpx",
                "profile_id": "safe-web-probe",
                "targets": ["https://example.com"],
                "options": {},
            },
        )


def test_existing_action_submission_can_render_async_accepted_contract() -> None:
    decision = PolicyDecision(
        action_id=uuid4(),
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=["https://example.com"],
    )
    response = ActionSubmission(
        action_id=decision.action_id,
        status=ActionStatus.QUEUED,
        message="Queued",
        job_id=uuid4(),
        run_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        policy_decision=decision,
        wait_url="/tool-actions/123/wait",
        events_url="/tool-actions/123/events",
        result_url="/tool-actions/123/result",
    )

    dumped = response.model_dump(mode="json")
    assert dumped["status"] == "queued"
    assert dumped["wait_url"].endswith("/wait")
    assert dumped["events_url"].endswith("/events")
    assert dumped["result_url"].endswith("/result")


def test_tool_invocation_carries_runner_context_and_options() -> None:
    ids = {
        name: uuid4()
        for name in [
            "action_id",
            "job_id",
            "run_id",
            "program_id",
            "scope_decision_id",
            "policy_decision_id",
            "campaign_id",
            "correlation_id",
        ]
    }

    parent_artifact_id = uuid4()
    invocation = ToolInvocation(
        **ids,
        capability_id="katana",
        profile_id="safe-crawl",
        targets=" https://example.com ",
        options={"depth": 3, "js_crawl": True},
        safety_level=SafetyLevel.SAFE_ACTIVE,
        execution_budget=ExecutionBudget(
            max_duration_seconds=60,
            max_targets=20,
            rate_per_second=10,
            concurrency=2,
        ),
        requested_by="api",
        source_event_id=uuid4(),
        parent_artifact_id=parent_artifact_id,
    )

    assert invocation.targets == ["https://example.com"]
    assert invocation.options == {"depth": 3, "js_crawl": True}
    assert invocation.execution_budget.concurrency == 2
    assert invocation.safety_level is SafetyLevel.SAFE_ACTIVE
    assert invocation.action_id == ids["action_id"]
    assert invocation.policy_decision_id == ids["policy_decision_id"]
    assert invocation.scope_decision_id == ids["scope_decision_id"]
    assert invocation.parent_artifact_id == parent_artifact_id


def test_build_invocation_reads_parent_artifact_from_event_payload() -> None:
    parent_artifact_id = uuid4()
    event = {
        "action_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "program_id": str(uuid4()),
        "capability_id": "httpx",
        "profile_id": "passive",
        "targets": ["https://example.com"],
        "execution_budget": {"max_targets": 5},
        "safety_level": "passive",
        "scope_decision_id": str(uuid4()),
        "policy_decision_id": str(uuid4()),
        "campaign_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "payload": {"parent_artifact_id": str(parent_artifact_id)},
    }

    invocation = build_invocation(event, event["targets"])

    assert invocation is not None
    assert invocation.parent_artifact_id == parent_artifact_id


def test_action_event_payload_keeps_options_in_one_nested_shape() -> None:
    action = ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=["https://example.com"],
        options={"timeout": 10, "follow_redirects": False},
    ).bind_profile(
        capability_id="httpx",
        profile_id="safe-web-probe",
        options={"timeout": 10, "follow_redirects": False},
        execution_budget=ExecutionBudget(max_targets=5),
    )
    decision = PolicyDecision(
        action_id=action.action_id,
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=action.targets,
    )

    payload = ActionEnvelopeBuilder.payload(action, decision, scope_id=uuid4())

    assert payload["options"] == {"timeout": 10, "follow_redirects": False}
    assert "timeout" not in payload
    assert "follow_redirects" not in payload


def test_tool_invocation_rejects_missing_policy_or_scope_reference() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(
            action_id=uuid4(),
            job_id=uuid4(),
            run_id=uuid4(),
            program_id=uuid4(),
            capability_id="httpx",
            profile_id="passive",
            targets=["https://example.com"],
            options={},
            safety_level=SafetyLevel.PASSIVE,
            execution_budget=ExecutionBudget(max_targets=5),
            campaign_id=uuid4(),
            correlation_id=uuid4(),
        )
