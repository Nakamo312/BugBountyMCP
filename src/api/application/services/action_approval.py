"""Approval and rejection workflow for pending actions."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import ActionStatus, ActionSubmission
from api.application.ports.action import ActionApprovalPort
from api.application.services.action_command import ActionCommandCompiler
from api.application.services.action_envelope import ActionEnvelopeBuilder
from api.application.services.action_errors import ActionApprovalStateError, ActionNotFoundError
from api.application.services.action_policy_evaluator import ActionPolicyEvaluator


class ActionApprovalWorkflow:
    """Coordinate approval decisions for actions already awaiting review."""

    def __init__(
        self,
        *,
        approvals: ActionApprovalPort,
        command_compiler: ActionCommandCompiler,
        policy_evaluator: ActionPolicyEvaluator,
        envelopes: ActionEnvelopeBuilder,
    ) -> None:
        self.approvals = approvals
        self.command_compiler = command_compiler
        self.policy_evaluator = policy_evaluator
        self.envelopes = envelopes

    async def approve_action(
        self,
        *,
        action_id: UUID,
        approved_by: str = "api",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        action, current_status = await self._action_for_approval(action_id)
        command, detail = await self.command_compiler.resolve_command(action)
        self._require_approval_status(action_id, current_status)
        decision = await self.policy_evaluator.approve(
            command,
            detail,
            approved_by=approved_by,
            reason=reason,
        )
        scope_id = await self.approvals.get_scope_id(command.action_id)
        envelope = self.envelopes.event_envelope(
            command,
            decision,
            request_event=detail.request_event,
            source=approved_by,
            confidence=confidence,
            scope_id=scope_id,
        )
        approved = await self.approvals.approve_and_create_queued_job(command, decision, envelope)
        if not approved:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )
        return self.envelopes.queued_submission(
            command,
            decision,
            envelope,
            message=_approved_message(detail.request_event, len(envelope.targets)),
        )

    async def reject_action(
        self,
        *,
        action_id: UUID,
        rejected_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        action, current_status = await self._action_for_approval(action_id)
        command, _detail = await self.command_compiler.resolve_command(action)
        self._require_approval_status(action_id, current_status)
        decision = self.policy_evaluator.reject(
            command,
            rejected_by=rejected_by,
            reason=reason,
        )
        rejected = await self.approvals.reject_action(command, decision)
        if not rejected:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )
        return self.envelopes.rejected_submission(command, decision)

    async def _action_for_approval(self, action_id: UUID):
        action, current_status = await self.approvals.get_action_for_approval(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        return action, current_status

    @staticmethod
    def _require_approval_status(action_id: UUID, current_status: str) -> None:
        if current_status != ActionStatus.REQUIRES_APPROVAL.value:
            raise ActionApprovalStateError(
                f"Action {action_id} is not awaiting approval: {current_status}"
            )


def _approved_message(request_event: str, target_count: int) -> str:
    label = request_event.replace("_", " ").title()
    return f"{label} approved and queued for {target_count} targets"
