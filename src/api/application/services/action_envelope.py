"""Event envelope and submission DTO builders for action commands."""
from __future__ import annotations

from uuid import UUID

from api.application.action_invocation_payload import (
    ACTION_INVOCATION_PAYLOAD_KEY,
    ACTION_INVOCATION_SCHEMA,
)
from api.application.contracts import (
    ResolvedActionCommand,
    ActionStatus,
    ActionSubmission,
    EventEnvelope,
    PolicyDecision,
)


class ActionEnvelopeBuilder:
    """Build durable event envelopes and public submission responses."""

    def event_envelope(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        request_event: str,
        source: str,
        confidence: float,
        scope_id: UUID | None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event=request_event,
            program_id=action.program_id,
            targets=decision.allowed_targets,
            source=source,
            confidence=confidence,
            correlation_id=action.correlation_id,
            campaign_id=action.campaign_id,
            expansion_depth=0,
            profile=action.profile.profile_id,
            payload=self.payload(action, decision, scope_id=scope_id),
        )

    @staticmethod
    def payload(
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        scope_id: UUID | None,
    ) -> dict[str, object]:
        invocation = {
            "schema": ACTION_INVOCATION_SCHEMA,
            "options": dict(action.profile.options),
            "action_id": str(action.action_id),
            "capability_id": action.profile.capability_id,
            "profile_id": action.profile.profile_id,
            "execution_budget": action.effective_budget.model_dump(mode="json"),
            "policy_decision_id": str(decision.decision_id),
            "scope_decision_id": str(scope_id) if scope_id is not None else None,
            "campaign_id": str(action.campaign_id),
            "requested_by": action.requested_by,
        }
        if decision.safety_level is not None:
            invocation["safety_level"] = decision.safety_level.value
        return {
            ACTION_INVOCATION_PAYLOAD_KEY: {
                key: value for key, value in invocation.items() if value is not None
            }
        }

    @staticmethod
    def terminal_submission(
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        *,
        status: ActionStatus,
        message: str,
    ) -> ActionSubmission:
        return ActionSubmission(
            action_id=action.action_id,
            status=status,
            message=message,
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            policy_decision=decision,
        )

    @staticmethod
    def queued_submission(
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        message: str,
    ) -> ActionSubmission:
        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message=message,
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            event_id=envelope.event_id,
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            policy_decision=decision,
        )

    @staticmethod
    def rejected_submission(
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> ActionSubmission:
        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.REJECTED,
            message=f"Action rejected for {len(action.profile.targets)} targets",
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            policy_decision=decision,
        )
