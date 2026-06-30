"""Command workflow for action submission and approval."""
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
from api.application.execution_limits import (
    DEFAULT_SYSTEM_EXECUTION_BUDGET,
    ExecutionBudget,
)
from api.application.ports.action import (
    ActionApprovalPort,
    ActionCommandPort,
    ScopeRuleProvider,
)
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.action_catalog_resolver import ActionCatalogResolver
from api.application.services.action_envelope import ActionEnvelopeBuilder
from api.application.services.action_errors import (
    ActionApprovalStateError,
    ActionNotFoundError,
)
from api.application.services.action_policy_evaluator import ActionPolicyEvaluator
from api.application.services.action_submission_recorder import ActionSubmissionRecorder
from api.application.services.policy import PolicyService

SubmissionLookup = Callable[[UUID], Awaitable[ActionSubmission | None]]


class ActionSubmissionWorkflow:
    """Coordinate action command use cases across small helper services."""

    def __init__(
        self,
        *,
        commands: ActionCommandPort,
        approvals: ActionApprovalPort,
        policy: PolicyService,
        catalog: ActionCatalogService,
        submission_lookup: SubmissionLookup,
        scope_rules: ScopeRuleProvider | None = None,
        system_budget: ExecutionBudget | None = None,
        resolver: ActionCatalogResolver | None = None,
        policy_evaluator: ActionPolicyEvaluator | None = None,
        envelopes: ActionEnvelopeBuilder | None = None,
        recorder: ActionSubmissionRecorder | None = None,
    ) -> None:
        budget = system_budget or DEFAULT_SYSTEM_EXECUTION_BUDGET
        self.approvals = approvals
        self.resolver = resolver or ActionCatalogResolver(catalog=catalog, system_budget=budget)
        self.policy_evaluator = policy_evaluator or ActionPolicyEvaluator(
            policy=policy,
            scope_rules=scope_rules,
        )
        self.envelopes = envelopes or ActionEnvelopeBuilder()
        self.recorder = recorder or ActionSubmissionRecorder(
            commands=commands,
            submission_lookup=submission_lookup,
        )
        self.submission_lookup = submission_lookup

    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        existing = await self.submission_lookup(action.action_id)
        if existing is not None:
            return existing
        command, detail = await self.resolver.resolve_command(action)
        decision = await self.policy_evaluator.evaluate(command, detail)
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
        detail = await self.resolver.resolve_scan_event(event=event, profile_id=profile_id)
        action = ActionRequest(
            kind=ActionKind.SCAN,
            program_id=program_id,
            catalog_id=detail.id,
            targets=targets,
            options=options or {},
            requested_by=requested_by,
        )
        return await self.request_action(action, confidence=confidence)

    async def approve_action(
        self,
        *,
        action_id: UUID,
        approved_by: str = "api",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        action, current_status = await self._action_for_approval(action_id)
        command, detail = await self.resolver.resolve_command(action)
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
            message=self._queued_message(detail.request_event, len(envelope.targets), approved=True),
        )

    async def reject_action(
        self,
        *,
        action_id: UUID,
        rejected_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        action, current_status = await self._action_for_approval(action_id)
        command, _detail = await self.resolver.resolve_command(action)
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

    async def _record_terminal_submission(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        status: ActionStatus,
        message: str,
    ) -> ActionSubmission:
        recovered = await self.recorder.record_policy_result_or_recover(action, decision)
        if recovered is not None:
            return recovered
        return self.envelopes.terminal_submission(
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
        envelope = self.envelopes.event_envelope(
            action,
            decision,
            request_event=request_event,
            source=source,
            confidence=confidence,
            scope_id=scope_id,
        )
        recovered = await self.recorder.create_allowed_action_or_recover(
            action,
            decision,
            envelope,
            scope_id=scope_id,
        )
        if recovered is not None:
            return recovered
        return self.envelopes.queued_submission(
            action,
            decision,
            envelope,
            message=self._queued_message(request_event, len(envelope.targets)),
        )

    @staticmethod
    def _queued_message(request_event: str, target_count: int, *, approved: bool = False) -> str:
        label = request_event.replace("_", " ").title()
        if approved:
            return f"{label} approved and queued for {target_count} targets"
        return f"{label} queued for {target_count} targets"
