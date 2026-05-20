"""Control-plane action service for scan requests."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.capabilities import CAPABILITY_BY_EVENT, CAPABILITY_BY_ID
from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
    ActionSubmission,
    EventEnvelope,
    PolicyDecisionStatus,
    ScanProfile,
)
from api.application.services.policy import PolicyService
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.orchestration.store import OrchestrationStore


class ActionService:
    """Validate, policy-check, persist, and enqueue scan actions."""

    def __init__(
        self,
        event_bus: EventBus,
        store: OrchestrationStore,
        policy: PolicyService,
    ):
        self.event_bus = event_bus
        self.store = store
        self.policy = policy

    async def list_actions(
        self,
        *,
        status: ActionStatus | None = None,
        program_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        return await self.store.list_actions(
            status=status.value if status else None,
            program_id=program_id,
            limit=limit,
            offset=offset,
        )

    async def approve_action(
        self,
        *,
        action_id: UUID,
        approved_by: str = "api",
        reason: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        action, current_status = await self.store.get_action_for_approval(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        if current_status != ActionStatus.REQUIRES_APPROVAL.value:
            raise ActionApprovalStateError(
                f"Action {action_id} is not awaiting approval: {current_status}"
            )

        capability = CAPABILITY_BY_ID.get(action.profile.capability_id)
        if capability is None:
            raise ActionApprovalStateError(
                f"Action {action_id} references unknown capability: {action.profile.capability_id}"
            )

        decision = self.policy.approve(
            action,
            approved_by=approved_by,
            reason=reason,
        )
        envelope = EventEnvelope(
            event=capability.request_event,
            program_id=action.program_id,
            targets=decision.allowed_targets,
            source=approved_by,
            confidence=confidence,
            profile=action.profile.profile_id,
            payload=action.profile.options,
        )
        approved = await self.store.approve_and_create_queued_job(action, decision, envelope)
        if not approved:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )
        await self.event_bus.publish(envelope)

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message=(
                f"{capability.request_event.replace('_', ' ').title()} approved "
                f"and queued for {len(envelope.targets)} targets"
            ),
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            event_id=envelope.event_id,
            policy_decision=decision,
        )

    async def reject_action(
        self,
        *,
        action_id: UUID,
        rejected_by: str = "api",
        reason: str | None = None,
    ) -> ActionSubmission:
        action, current_status = await self.store.get_action_for_approval(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        if current_status != ActionStatus.REQUIRES_APPROVAL.value:
            raise ActionApprovalStateError(
                f"Action {action_id} is not awaiting approval: {current_status}"
            )

        decision = self.policy.reject(
            action,
            rejected_by=rejected_by,
            reason=reason,
        )
        rejected = await self.store.reject_action(action, decision)
        if not rejected:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.REJECTED,
            message=f"Action rejected for {len(action.profile.targets)} targets",
            policy_decision=decision,
        )

    async def request_scan(
        self,
        *,
        event: str,
        program_id: UUID,
        targets: list[str],
        options: dict[str, Any] | None = None,
        requested_by: str = "api",
        profile_id: str | None = None,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        capability = CAPABILITY_BY_EVENT.get(event)
        if capability is None:
            profile = ScanProfile(
                capability_id="unknown",
                profile_id="unknown",
                targets=targets,
                options=options or {},
            )
        else:
            profile = ScanProfile(
                capability_id=capability.id,
                profile_id=profile_id or capability.default_profile,
                targets=targets,
                options=options or {},
            )

        action = ActionRequest(
            kind=ActionKind.SCAN,
            program_id=program_id,
            profile=profile,
            requested_by=requested_by,
        )
        decision = self.policy.evaluate(action)
        await self.store.record_policy_result(action, decision)

        if decision.status == PolicyDecisionStatus.BLOCKED:
            return ActionSubmission(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                message="Action blocked by policy",
                policy_decision=decision,
            )

        if decision.status == PolicyDecisionStatus.REQUIRES_APPROVAL:
            return ActionSubmission(
                action_id=action.action_id,
                status=ActionStatus.REQUIRES_APPROVAL,
                message="Action requires approval before enqueue",
                policy_decision=decision,
            )

        envelope = EventEnvelope(
            event=event,
            program_id=program_id,
            targets=decision.allowed_targets,
            source=requested_by,
            confidence=confidence,
            profile=profile.profile_id,
            payload=profile.options,
        )
        await self.store.create_queued_job(action, envelope)
        await self.event_bus.publish(envelope)

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message=f"{event.replace('_', ' ').title()} queued for {len(envelope.targets)} targets",
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            event_id=envelope.event_id,
            policy_decision=decision,
        )


class ActionNotFoundError(Exception):
    """Raised when an action transition targets an unknown action."""


class ActionApprovalStateError(Exception):
    """Raised when an action cannot be approved from its current state."""
