"""Control-plane action service façade."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import (
    ActionEventRecord,
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionRecord,
    ActionRequest,
    ActionResultRecord,
    ActionStatus,
    ActionSubmission,
)
from api.application.services.action_approval import ActionApprovalWorkflow
from api.application.services.action_control import ActionControlService
from api.application.services.action_errors import ActionApprovalStateError
from api.application.services.action_outcome_feedback import ActionOutcomeFeedbackService
from api.application.services.action_read import ActionReadService
from api.application.services.action_submission import ActionSubmissionWorkflow


class ActionService:
    """Thin façade over already-composed action use cases."""

    def __init__(
        self,
        *,
        reads: ActionReadService,
        feedback: ActionOutcomeFeedbackService,
        submissions: ActionSubmissionWorkflow,
        approvals: ActionApprovalWorkflow,
    ) -> None:
        self._reads = reads
        self._feedback = feedback
        self._submissions = submissions
        self._approvals = approvals
        self._controls: ActionControlService | None = None

    async def list_actions(
        self,
        *,
        status: ActionStatus | None = None,
        program_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        return await self._reads.list_actions(
            status=status,
            program_id=program_id,
            limit=limit,
            offset=offset,
        )

    async def get_action(self, action_id: UUID) -> ActionRecord:
        return await self._reads.get_action(action_id)

    async def get_action_submission(self, action_id: UUID) -> ActionSubmission | None:
        return await self._reads.get_action_submission(action_id)

    async def list_action_events(
        self,
        action_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        return await self._reads.list_action_events(action_id, limit=limit, offset=offset)

    async def get_action_result(self, action_id: UUID) -> ActionResultRecord:
        return await self._reads.get_action_result(action_id)

    async def record_outcome_feedback(
        self,
        *,
        action_id: UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord:
        return await self._feedback.record_outcome_feedback(action_id=action_id, feedback=feedback)

    async def approve_action(
        self,
        *,
        action_id: UUID,
        approved_by: str = "api",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        return await self._approvals.approve_action(
            action_id=action_id,
            approved_by=approved_by,
            reason=reason,
            confidence=confidence,
        )

    async def reject_action(
        self,
        *,
        action_id: UUID,
        rejected_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        return await self._approvals.reject_action(
            action_id=action_id,
            rejected_by=rejected_by,
            reason=reason,
        )


    def with_controls(self, controls: ActionControlService) -> "ActionService":
        self._controls = controls
        return self

    async def cancel_action(
        self,
        *,
        action_id: UUID,
        cancelled_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        if self._controls is None:
            raise ActionApprovalStateError("Action cancellation controls are not configured")
        return await self._controls.cancel_action(
            action_id=action_id,
            cancelled_by=cancelled_by,
            reason=reason,
        )

    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        return await self._submissions.request_action(action, confidence=confidence)

    async def request_scan(
        self,
        *,
        event: str,
        program_id: UUID,
        targets: list[str],
        options: dict | None = None,
        requested_by: str = "api",
        profile_id: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        return await self._submissions.request_scan(
            event=event,
            program_id=program_id,
            targets=targets,
            options=options,
            requested_by=requested_by,
            profile_id=profile_id,
            confidence=confidence,
        )
