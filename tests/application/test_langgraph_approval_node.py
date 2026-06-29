from __future__ import annotations

from uuid import UUID, uuid4

from api.application.contracts import (
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.langgraph_approval import (
    LangGraphApprovalNode,
    LangGraphApprovalRequest,
)
from api.application.langgraph_tool_action import LangGraphToolActionRequest
from api.application.langgraph_workflows import LangGraphWorkflowState


def submission(status: ActionStatus) -> ActionSubmission:
    decision_status = {
        ActionStatus.QUEUED: PolicyDecisionStatus.ALLOWED,
        ActionStatus.REJECTED: PolicyDecisionStatus.REJECTED,
        ActionStatus.REQUIRES_APPROVAL: PolicyDecisionStatus.REQUIRES_APPROVAL,
        ActionStatus.BLOCKED: PolicyDecisionStatus.BLOCKED,
    }[status]
    decision = PolicyDecision(
        action_id=uuid4(),
        status=decision_status,
        allowed_targets=["https://example.com"] if status is ActionStatus.QUEUED else [],
    )
    return ActionSubmission(
        action_id=decision.action_id,
        status=status,
        message=status.value,
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        workflow_id=uuid4(),
        policy_decision=decision,
    )


def workflow_state(*, run_id: UUID, status: str) -> LangGraphWorkflowState:
    return LangGraphWorkflowState(
        workflow_id=uuid4(),
        run_id=run_id,
        program_id=uuid4(),
        campaign_id=None,
        correlation_id=uuid4(),
        workflow_type="surface_hypothesis",
        status=status,
        current_node="approval",
        checkpoint_ref="pg-checkpoint:approval",
        action_ids=(),
        wait_condition_ids=(),
        result_set_keys=(),
    )


class RecordingTool:
    def __init__(self, result: ActionSubmission) -> None:
        self.result = result
        self.requests = []

    async def create_action(self, request):
        self.requests.append(request)
        return self.result


class RecordingApprovalService:
    def __init__(
        self,
        *,
        approved: ActionSubmission | None = None,
        rejected: ActionSubmission | None = None,
    ) -> None:
        self.approved = approved
        self.rejected = rejected
        self.approve_calls = []
        self.reject_calls = []

    async def approve_action(self, *, action_id, approved_by="api", reason=None, confidence=0.5):
        self.approve_calls.append((action_id, approved_by, reason, confidence))
        return self.approved

    async def reject_action(self, *, action_id, rejected_by="api", reason=None):
        self.reject_calls.append((action_id, rejected_by, reason))
        return self.rejected


class RecordingRuntime:
    def __init__(self) -> None:
        self.paused = []
        self.resumed = []
        self.cancelled = []

    async def pause(self, *, run_id, checkpoint_ref, current_node, wait_condition_id=None):
        self.paused.append((run_id, checkpoint_ref, current_node, wait_condition_id))
        return workflow_state(run_id=run_id, status="waiting")

    async def resume(self, *, run_id, checkpoint_ref=None):
        self.resumed.append((run_id, checkpoint_ref))
        return workflow_state(run_id=run_id, status="running")

    async def cancel(self, *, run_id, reason=None):
        self.cancelled.append((run_id, reason))
        return workflow_state(run_id=run_id, status="cancelled")


async def test_approval_node_pauses_workflow_when_action_requires_approval() -> None:
    run_id = uuid4()
    runtime = RecordingRuntime()
    node = LangGraphApprovalNode(
        tool=RecordingTool(submission(ActionStatus.REQUIRES_APPROVAL)),
        approval_service=RecordingApprovalService(),
        workflow_runtime=runtime,
    )

    result = await node.request_or_pause(
        LangGraphApprovalRequest(
            workflow_run_id=run_id,
            checkpoint_ref="pg-checkpoint:approval",
            current_node="approval",
            action=LangGraphToolActionRequest(
                program_id=uuid4(),
                catalog_id=uuid4(),
                targets=["https://example.com"],
            ),
        )
    )

    assert result.submission.status is ActionStatus.REQUIRES_APPROVAL
    assert result.workflow_state.status == "waiting"
    assert result.paused is True
    assert runtime.paused == [(run_id, "pg-checkpoint:approval", "approval", None)]
    assert runtime.resumed == []
    assert runtime.cancelled == []


async def test_approval_node_resumes_workflow_after_human_approval() -> None:
    run_id = uuid4()
    approved = submission(ActionStatus.QUEUED)
    runtime = RecordingRuntime()
    approval = RecordingApprovalService(approved=approved)
    node = LangGraphApprovalNode(
        tool=RecordingTool(approved),
        approval_service=approval,
        workflow_runtime=runtime,
    )

    result = await node.approve_and_resume(
        action_id=approved.action_id,
        workflow_run_id=run_id,
        checkpoint_ref="pg-checkpoint:approval",
        approved_by="human",
        reason="inside scope",
    )

    assert result.submission.status is ActionStatus.QUEUED
    assert result.workflow_state.status == "running"
    assert result.resumed is True
    assert approval.approve_calls == [
        (approved.action_id, "human", "inside scope", 0.5),
    ]
    assert runtime.resumed == [(run_id, "pg-checkpoint:approval")]


async def test_approval_node_rejects_action_and_cancels_workflow() -> None:
    run_id = uuid4()
    rejected = submission(ActionStatus.REJECTED)
    runtime = RecordingRuntime()
    approval = RecordingApprovalService(rejected=rejected)
    node = LangGraphApprovalNode(
        tool=RecordingTool(rejected),
        approval_service=approval,
        workflow_runtime=runtime,
    )

    result = await node.reject_and_cancel(
        action_id=rejected.action_id,
        workflow_run_id=run_id,
        rejected_by="human",
        reason="out of scope",
    )

    assert result.submission.status is ActionStatus.REJECTED
    assert result.workflow_state.status == "cancelled"
    assert result.cancelled is True
    assert approval.reject_calls == [(rejected.action_id, "human", "out of scope")]
    assert runtime.cancelled == [(run_id, "out of scope")]


def test_langgraph_approval_node_does_not_import_execution_surfaces() -> None:
    source = open("src/api/application/langgraph_approval.py", encoding="utf-8").read()

    assert "request_action" not in source
    for forbidden in ("RabbitMQ", "EventBus", "runner", "subprocess", "session", "store."):
        assert forbidden not in source
