"""Control-plane action service for scan requests."""
from __future__ import annotations

from uuid import UUID

from api.application.action_catalog import CatalogDetail
from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
    ActionSubmission,
    EventEnvelope,
    PolicyDecisionStatus,
)
from api.application.services.action_catalog import ActionCatalogService
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
        catalog: ActionCatalogService,
    ):
        self.event_bus = event_bus
        self.store = store
        self.policy = policy
        self.catalog = catalog

    async def _resolve(self, action: ActionRequest) -> CatalogDetail:
        detail = await self.catalog.get_detail(action.catalog_id)
        action.bind_profile(
            capability_id=detail.capability,
            profile_id=detail.profile,
        )
        action.metadata = {
            **action.metadata,
            "catalog_entry_id": str(detail.id),
            "catalog_snapshot_id": str(detail.snapshot_id),
        }
        return detail

    @staticmethod
    def _attach_catalog(action: ActionRequest, decision) -> None:
        decision.metadata = {
            **decision.metadata,
            "catalog_entry_id": str(action.catalog_id),
            "catalog_snapshot_id": action.metadata.get("catalog_snapshot_id"),
        }

    @staticmethod
    def _payload(
        action: ActionRequest,
        decision,
        *,
        scope_id: UUID | None,
    ) -> dict:
        options = dict(action.profile.options)
        payload = {
            **options,
            "options": options,
            "action_id": str(action.action_id),
            "capability_id": action.profile.capability_id,
            "profile_id": action.profile.profile_id,
            "policy_decision_id": str(decision.decision_id),
            "scope_decision_id": str(scope_id) if scope_id is not None else None,
            "campaign_id": str(action.campaign_id),
            "requested_by": action.requested_by,
        }
        if decision.safety_level is not None:
            payload["safety_level"] = decision.safety_level.value
        return {key: value for key, value in payload.items() if value is not None}

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
        detail = await self._resolve(action)
        if current_status != ActionStatus.REQUIRES_APPROVAL.value:
            raise ActionApprovalStateError(
                f"Action {action_id} is not awaiting approval: {current_status}"
            )

        decision = self.policy.approve(
            action,
            detail,
            approved_by=approved_by,
            reason=reason,
        )
        self._attach_catalog(action, decision)
        scope_id = await self.store.get_scope_id(action.action_id)
        envelope = EventEnvelope(
            event=detail.request_event,
            program_id=action.program_id,
            targets=decision.allowed_targets,
            source=approved_by,
            confidence=confidence,
            profile=action.profile.profile_id,
            payload=self._payload(action, decision, scope_id=scope_id),
        )
        approved = await self.store.approve_and_create_queued_job(action, decision, envelope)
        if not approved:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message=(
                f"{detail.request_event.replace('_', ' ').title()} approved "
                f"and queued for {len(envelope.targets)} targets"
            ),
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            event_id=envelope.event_id,
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
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
        await self._resolve(action)
        if current_status != ActionStatus.REQUIRES_APPROVAL.value:
            raise ActionApprovalStateError(
                f"Action {action_id} is not awaiting approval: {current_status}"
            )

        decision = self.policy.reject(
            action,
            rejected_by=rejected_by,
            reason=reason,
        )
        self._attach_catalog(action, decision)
        rejected = await self.store.reject_action(action, decision)
        if not rejected:
            raise ActionApprovalStateError(
                f"Action {action_id} is no longer awaiting approval"
            )

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.REJECTED,
            message=f"Action rejected for {len(action.profile.targets)} targets",
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            policy_decision=decision,
        )

    async def request_action(
        self,
        action: ActionRequest,
        *,
        confidence: float = 0.5,
    ) -> ActionSubmission:
        detail = await self._resolve(action)
        event = detail.request_event

        decision = self.policy.evaluate(action, detail)
        self._attach_catalog(action, decision)
        scope_id = await self.store.record_policy_result(action, decision)

        if decision.status == PolicyDecisionStatus.BLOCKED:
            return ActionSubmission(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                message="Action blocked by policy",
                campaign_id=action.campaign_id,
                correlation_id=action.correlation_id,
                workflow_id=action.workflow_id,
                policy_decision=decision,
            )

        if decision.status == PolicyDecisionStatus.REQUIRES_APPROVAL:
            return ActionSubmission(
                action_id=action.action_id,
                status=ActionStatus.REQUIRES_APPROVAL,
                message="Action requires approval before enqueue",
                campaign_id=action.campaign_id,
                correlation_id=action.correlation_id,
                workflow_id=action.workflow_id,
                policy_decision=decision,
            )

        envelope = EventEnvelope(
            event=event,
            program_id=action.program_id,
            targets=decision.allowed_targets,
            source=action.requested_by,
            confidence=confidence,
            profile=action.profile.profile_id,
            payload=self._payload(action, decision, scope_id=scope_id),
        )
        await self.store.create_queued_job(action, envelope)

        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message=f"{event.replace('_', ' ').title()} queued for {len(envelope.targets)} targets",
            job_id=envelope.job_id,
            run_id=envelope.run_id,
            event_id=envelope.event_id,
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            policy_decision=decision,
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
        detail = await self.catalog.find_detail_by_event(event=event, profile=profile_id)
        action = ActionRequest(
            kind=ActionKind.SCAN,
            program_id=program_id,
            catalog_id=detail.id,
            targets=targets,
            options=options or {},
            requested_by=requested_by,
        )
        return await self.request_action(action, confidence=confidence)


class ActionNotFoundError(Exception):
    """Raised when an action transition targets an unknown action."""


class ActionApprovalStateError(Exception):
    """Raised when an action cannot be approved from its current state."""
