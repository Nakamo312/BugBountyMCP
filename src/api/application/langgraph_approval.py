"""LangGraph approval node adapter.

This module coordinates LangGraph workflow state with the existing control-plane
approval API. It does not approve policy itself and it does not enqueue work
directly; those transitions stay inside ActionService.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from api.application.contracts import ActionStatus, ActionSubmission
from api.application.langgraph_tool_action import (
    LangGraphToolActionRequest,
    LangGraphToolActionTool,
)
from api.application.langgraph_workflows import (
    LangGraphWorkflowRuntime,
    LangGraphWorkflowState,
)


@dataclass(frozen=True, slots=True)
class LangGraphApprovalRequest:
    workflow_run_id: UUID
    checkpoint_ref: str
    current_node: str
    action: LangGraphToolActionRequest


@dataclass(frozen=True, slots=True)
class LangGraphApprovalResult:
    submission: ActionSubmission
    workflow_state: LangGraphWorkflowState | None = None
    paused: bool = False
    resumed: bool = False
    cancelled: bool = False


class ApprovalService(Protocol):
    async def approve_action(
        self,
        *,
        action_id: UUID,
        approved_by: str = "api",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission: ...

    async def reject_action(
        self,
        *,
        action_id: UUID,
        rejected_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission: ...


class LangGraphApprovalNode:
    """Thin node for human approval wait/resume semantics."""

    def __init__(
        self,
        *,
        tool: LangGraphToolActionTool,
        approval_service: ApprovalService,
        workflow_runtime: LangGraphWorkflowRuntime,
    ) -> None:
        self.tool = tool
        self.approval_service = approval_service
        self.workflow_runtime = workflow_runtime

    async def request_or_pause(
        self,
        request: LangGraphApprovalRequest,
    ) -> LangGraphApprovalResult:
        submission = await self.tool.create_action(request.action)
        if submission.status != ActionStatus.REQUIRES_APPROVAL:
            return LangGraphApprovalResult(submission=submission)

        state = await self.workflow_runtime.pause(
            run_id=request.workflow_run_id,
            checkpoint_ref=request.checkpoint_ref,
            current_node=request.current_node,
        )
        return LangGraphApprovalResult(
            submission=submission,
            workflow_state=state,
            paused=True,
        )

    async def approve_and_resume(
        self,
        *,
        action_id: UUID,
        workflow_run_id: UUID,
        checkpoint_ref: str | None = None,
        approved_by: str = "human",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> LangGraphApprovalResult:
        submission = await self.approval_service.approve_action(
            action_id=action_id,
            approved_by=approved_by,
            reason=reason,
            confidence=confidence,
        )
        if submission.status != ActionStatus.QUEUED:
            return LangGraphApprovalResult(submission=submission)

        state = await self.workflow_runtime.resume(
            run_id=workflow_run_id,
            checkpoint_ref=checkpoint_ref,
        )
        return LangGraphApprovalResult(
            submission=submission,
            workflow_state=state,
            resumed=True,
        )

    async def reject_and_cancel(
        self,
        *,
        action_id: UUID,
        workflow_run_id: UUID,
        rejected_by: str = "human",
        reason: str | None = None,
    ) -> LangGraphApprovalResult:
        submission = await self.approval_service.reject_action(
            action_id=action_id,
            rejected_by=rejected_by,
            reason=reason,
        )
        state = await self.workflow_runtime.cancel(
            run_id=workflow_run_id,
            reason=reason,
        )
        return LangGraphApprovalResult(
            submission=submission,
            workflow_state=state,
            cancelled=True,
        )
