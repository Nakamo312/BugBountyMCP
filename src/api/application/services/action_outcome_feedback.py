"""Outcome-feedback write workflow for action results."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import (
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
)
from api.application.ports.action import ActionOutcomeFeedbackWriter, ActionQueryPort
from api.application.services.action_errors import (
    ActionNotFoundError,
    ActionOutcomeFeedbackUnavailable,
    ActionOutcomeNotFoundError,
)


class ActionOutcomeFeedbackService:
    """Record human/workflow feedback without pretending to be a read service."""

    def __init__(
        self,
        *,
        queries: ActionQueryPort,
        outcome_feedback: ActionOutcomeFeedbackWriter | None = None,
    ) -> None:
        self.queries = queries
        self.outcome_feedback = outcome_feedback

    async def record_outcome_feedback(
        self,
        *,
        action_id: UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord:
        action = await self.queries.get_action(action_id)
        if action is None:
            raise ActionNotFoundError(f"Action not found: {action_id}")
        if self.outcome_feedback is None:
            raise ActionOutcomeFeedbackUnavailable("Action outcome feedback is not configured")
        record = await self.outcome_feedback.apply_feedback(
            action_id=action_id,
            feedback=feedback,
        )
        if record is None:
            raise ActionOutcomeNotFoundError(f"Action outcome not found: {action_id}")
        return record
