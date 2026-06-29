from __future__ import annotations

from uuid import uuid4

from api.application.contracts import (
    ActionKind,
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.langgraph_tool_action import (
    LangGraphToolActionRequest,
    LangGraphToolActionTool,
)


class RecordingActionService:
    def __init__(self, submission: ActionSubmission) -> None:
        self.submission = submission
        self.requests = []

    async def request_action(self, request):
        self.requests.append(request)
        return self.submission


async def test_langgraph_tool_action_creates_action_through_action_service_only() -> None:
    workflow_id = uuid4()
    campaign_id = uuid4()
    correlation_id = uuid4()
    decision = PolicyDecision(
        action_id=uuid4(),
        status=PolicyDecisionStatus.ALLOWED,
        allowed_targets=["https://example.com"],
    )
    service = RecordingActionService(
        ActionSubmission(
            action_id=decision.action_id,
            status=ActionStatus.QUEUED,
            message="Queued",
            job_id=uuid4(),
            run_id=uuid4(),
            event_id=uuid4(),
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            policy_decision=decision,
        )
    )
    tool = LangGraphToolActionTool(action_service=service)

    submission = await tool.create_action(
        LangGraphToolActionRequest(
            program_id=uuid4(),
            catalog_id=uuid4(),
            targets=["https://example.com"],
            options={"timeout": 10},
            workflow_id=workflow_id,
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            metadata={"node": "probe"},
        )
    )

    assert submission.status is ActionStatus.QUEUED
    assert len(service.requests) == 1
    request = service.requests[0]
    assert request.kind is ActionKind.SCAN
    assert request.requested_by == "langgraph"
    assert request.workflow_id == workflow_id
    assert request.campaign_id == campaign_id
    assert request.correlation_id == correlation_id
    assert request.metadata["node"] == "probe"
    assert request.metadata["langgraph_tool"] is True


async def test_langgraph_tool_action_surfaces_approval_required_without_bypassing_policy() -> None:
    decision = PolicyDecision(
        action_id=uuid4(),
        status=PolicyDecisionStatus.REQUIRES_APPROVAL,
        reasons=["sensitive action"],
    )
    service = RecordingActionService(
        ActionSubmission(
            action_id=decision.action_id,
            status=ActionStatus.REQUIRES_APPROVAL,
            message="Action requires approval before enqueue",
            campaign_id=uuid4(),
            correlation_id=uuid4(),
            workflow_id=uuid4(),
            policy_decision=decision,
        )
    )
    tool = LangGraphToolActionTool(action_service=service)

    submission = await tool.create_action(
        LangGraphToolActionRequest(
            program_id=uuid4(),
            catalog_id=uuid4(),
            targets=["https://example.com"],
        )
    )

    assert submission.status is ActionStatus.REQUIRES_APPROVAL
    assert submission.policy_decision.status is PolicyDecisionStatus.REQUIRES_APPROVAL
    assert service.requests[0].requested_by == "langgraph"


def test_langgraph_tool_action_does_not_import_execution_surfaces() -> None:
    source = open("src/api/application/langgraph_tool_action.py", encoding="utf-8").read()
    di_source = open("src/api/application/di.py", encoding="utf-8").read()

    assert "ActionRequest" in source
    assert "request_action" in source
    assert "LangGraphToolActionTool" in di_source
    assert "get_langgraph_tool_action_tool" in di_source
    for forbidden in ("RabbitMQ", "EventBus", "runner", "subprocess", "session", "store."):
        assert forbidden not in source
