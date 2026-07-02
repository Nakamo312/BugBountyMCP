"""Operator controls for already-created action requests."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import ActionStatus, ActionSubmission, PolicyDecision, PolicyDecisionStatus
from api.application.ports.action import ActionControlPort
from api.application.services.action_errors import ActionApprovalStateError, ActionNotFoundError


class ActionControlService:
    """Cancel queue entries without bypassing the existing execution boundary."""

    def __init__(self, *, controls: ActionControlPort) -> None:
        self.controls = controls

    async def cancel_action(
        self,
        *,
        action_id: UUID,
        cancelled_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        result = await self.controls.cancel_action(
            action_id=action_id,
            cancelled_by=cancelled_by,
            reason=reason,
        )
        if result is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        if not result.cancelled:
            raise ActionApprovalStateError(result.message)
        return ActionSubmission(
            action_id=action_id,
            status=ActionStatus.REJECTED,
            message=result.message,
            campaign_id=result.campaign_id,
            correlation_id=result.correlation_id,
            workflow_id=result.workflow_id,
            policy_decision=PolicyDecision(
                action_id=action_id,
                status=PolicyDecisionStatus.REJECTED,
                reasons=[result.message],
            ),
        )
