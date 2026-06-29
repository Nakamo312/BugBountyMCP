"""Read/query side helpers for action control-plane service."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import (
    ActionEventRecord,
    ActionRecord,
    ActionResultRecord,
    ActionStatus,
    ActionSubmission,
    ExecutionStatus,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.ports.action import ActionQueryPort, ActionResultPort
from api.application.services.action_errors import ActionNotFoundError


class ActionReadService:
    """Serve action read models only."""

    def __init__(
        self,
        *,
        queries: ActionQueryPort,
        results: ActionResultPort,
    ) -> None:
        self.queries = queries
        self.results = results

    async def list_actions(
        self,
        *,
        status: ActionStatus | None = None,
        program_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        return await self.queries.list_actions(
            status=status.value if status else None,
            program_id=program_id,
            limit=limit,
            offset=offset,
        )

    async def get_action(self, action_id: UUID) -> ActionRecord:
        action = await self.queries.get_action(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        return action

    async def get_action_submission(self, action_id: UUID) -> ActionSubmission | None:
        """Return an idempotency recovery view for an already-created action."""

        get_action = getattr(self.queries, "get_action", None)
        if get_action is None:
            return None
        action = await get_action(action_id)
        if action is None:
            return None
        return ActionSubmission(
            action_id=action.action_id,
            status=action.status,
            message=f"Existing action is {action.status.value}",
            campaign_id=getattr(action, "campaign_id", None),
            correlation_id=getattr(action, "correlation_id", None),
            workflow_id=getattr(action, "workflow_id", None),
            policy_decision=PolicyDecision(
                action_id=action.action_id,
                status=policy_decision_status_for_action_status(action.status),
            ),
        )

    async def list_action_events(
        self,
        action_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        await self.get_action(action_id)
        return await self.queries.list_action_events(
            action_id,
            limit=limit,
            offset=offset,
        )

    async def get_action_result(self, action_id: UUID) -> ActionResultRecord:
        action = await self.get_action(action_id)
        runs = await self.results.list_action_runs(action_id)
        artifacts = await self.results.list_action_artifacts(action_id)
        terminal_statuses = {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.DEAD,
            ExecutionStatus.CANCELLED,
        }
        ready = action.status in {ActionStatus.BLOCKED, ActionStatus.REJECTED} or (
            bool(runs) and all(run.status in terminal_statuses for run in runs)
        )
        return ActionResultRecord(
            action_id=action.action_id,
            action_status=action.status,
            ready=ready,
            runs=runs,
            artifacts=artifacts,
        )



def policy_decision_status_for_action_status(status: ActionStatus) -> PolicyDecisionStatus:
    if status is ActionStatus.QUEUED:
        return PolicyDecisionStatus.ALLOWED
    if status is ActionStatus.BLOCKED:
        return PolicyDecisionStatus.BLOCKED
    if status is ActionStatus.REQUIRES_APPROVAL:
        return PolicyDecisionStatus.REQUIRES_APPROVAL
    if status is ActionStatus.REJECTED:
        return PolicyDecisionStatus.REJECTED
    return PolicyDecisionStatus.ALLOWED
