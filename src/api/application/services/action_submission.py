"""Action request submission workflow."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from api.application.contracts import (
    ActionKind,
    ActionRequest,
    ResolvedActionCommand,
    ActionStatus,
    ActionSubmission,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.services.action_command import ActionCommandCompiler
from api.application.services.action_envelope import ActionEnvelopeBuilder
from api.application.services.action_policy_evaluator import ActionPolicyEvaluator
from api.application.services.action_submission_recorder import ActionSubmissionRecorder

SubmissionLookup = Callable[[UUID], Awaitable[ActionSubmission | None]]


class ActionSubmissionWorkflow:
    """Coordinate action request and enqueue use cases."""

    def __init__(
        self,
        *,
        command_compiler: ActionCommandCompiler,
        policy_evaluator: ActionPolicyEvaluator,
        envelopes: ActionEnvelopeBuilder,
        recorder: ActionSubmissionRecorder,
        submission_lookup: SubmissionLookup,
    ) -> None:
        self._command_compiler = command_compiler
        self._policy_evaluator = policy_evaluator
        self._envelopes = envelopes
        self._recorder = recorder
        self._submission_lookup = submission_lookup

    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        existing = await self._submission_lookup(action.action_id)
        if existing is not None:
            return existing
        command, detail = await self._command_compiler.resolve_command(action)
        decision = await self._policy_evaluator.evaluate(command, detail)
        if decision.status == PolicyDecisionStatus.BLOCKED:
            return await self._record_terminal_submission(
                command,
                decision,
                status=ActionStatus.BLOCKED,
                message="Action blocked by policy",
            )
        if decision.status == PolicyDecisionStatus.REQUIRES_APPROVAL:
            return await self._record_terminal_submission(
                command,
                decision,
                status=ActionStatus.REQUIRES_APPROVAL,
                message="Action requires approval before enqueue",
            )
        return await self._queue_allowed_action(
            command,
            decision,
            request_event=detail.request_event,
            source=command.requested_by,
            confidence=confidence,
        )

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
        detail = await self._command_compiler.resolve_scan_event(
            event=event,
            profile_id=profile_id,
        )
        action = ActionRequest(
            kind=ActionKind.SCAN,
            program_id=program_id,
            catalog_id=detail.id,
            targets=targets,
            options=options or {},
            requested_by=requested_by,
        )
        return await self.request_action(action, confidence=confidence)

    async def _record_terminal_submission(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        status: ActionStatus,
        message: str,
    ) -> ActionSubmission:
        recovered = await self._recorder.record_policy_result_or_recover(action, decision)
        if recovered is not None:
            return recovered
        return self._envelopes.terminal_submission(
            action,
            decision,
            status=status,
            message=message,
        )

    async def _queue_allowed_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        request_event: str,
        source: str,
        confidence: float,
    ) -> ActionSubmission:
        scope_id = uuid4()
        envelope = self._envelopes.event_envelope(
            action,
            decision,
            request_event=request_event,
            source=source,
            confidence=confidence,
            scope_id=scope_id,
        )
        recovered = await self._recorder.create_allowed_action_or_recover(
            action,
            decision,
            envelope,
            scope_id=scope_id,
        )
        if recovered is not None:
            return recovered
        return self._envelopes.queued_submission(
            action,
            decision,
            envelope,
            message=_queued_message(request_event, len(envelope.targets)),
        )


def _queued_message(request_event: str, target_count: int) -> str:
    label = request_event.replace("_", " ").title()
    return f"{label} queued for {target_count} targets"
