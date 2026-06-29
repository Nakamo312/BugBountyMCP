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
from api.application.execution_limits import DEFAULT_SYSTEM_EXECUTION_BUDGET, ExecutionBudget
from api.application.ports.action import (
    ActionApprovalPort,
    ActionCommandPort,
    ActionOutcomeFeedbackWriter,
    ActionQueryPort,
    ActionResultPort,
    ActionStorePort,
    ScopeRuleProvider,
)
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.action_errors import (
    ActionApprovalStateError,
    ActionNotFoundError,
    ActionOutcomeFeedbackUnavailable,
    ActionOutcomeNotFoundError,
)
from api.application.services.action_outcome_feedback import ActionOutcomeFeedbackService
from api.application.services.action_read import (
    ActionReadService,
    policy_decision_status_for_action_status as _policy_decision_status_for_action_status,
)
from api.application.services.action_submission import ActionSubmissionWorkflow
from api.application.services.policy import PolicyService


class ActionService:
    """Thin façade over action read and command use cases."""

    def __init__(
        self,
        store: ActionStorePort | None = None,
        policy: PolicyService | None = None,
        catalog: ActionCatalogService | None = None,
        scope_rules: ScopeRuleProvider | None = None,
        outcome_feedback: ActionOutcomeFeedbackWriter | None = None,
        system_budget: ExecutionBudget | None = None,
        commands: ActionCommandPort | None = None,
        queries: ActionQueryPort | None = None,
        results: ActionResultPort | None = None,
        approvals: ActionApprovalPort | None = None,
    ) -> None:
        self.commands = commands or store
        self.queries = queries or store
        self.results = results or store
        self.approvals = approvals or store
        if self.commands is None or self.queries is None or self.results is None or self.approvals is None:
            raise TypeError("ActionService requires command, query, result, and approval ports")
        if policy is None or catalog is None:
            raise TypeError("ActionService requires policy and catalog services")
        self.policy = policy
        self.catalog = catalog
        self.scope_rules = scope_rules
        self.outcome_feedback = outcome_feedback
        self.system_budget = system_budget or DEFAULT_SYSTEM_EXECUTION_BUDGET
        self._reads = ActionReadService(
            queries=self.queries,
            results=self.results,
        )
        self._feedback = ActionOutcomeFeedbackService(
            queries=self.queries,
            outcome_feedback=outcome_feedback,
        )
        self._submissions = ActionSubmissionWorkflow(
            commands=self.commands,
            approvals=self.approvals,
            policy=policy,
            catalog=catalog,
            scope_rules=scope_rules,
            system_budget=self.system_budget,
            submission_lookup=self._reads.get_action_submission,
        )

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
        return await self._submissions.approve_action(
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
        return await self._submissions.reject_action(
            action_id=action_id,
            rejected_by=rejected_by,
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
