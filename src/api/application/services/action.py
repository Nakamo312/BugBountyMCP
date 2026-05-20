"""Control-plane action service for scan requests."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.capabilities import CAPABILITY_BY_EVENT
from api.application.contracts import (
    ActionKind,
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
