"""Application service for recording scored action outcomes."""
from __future__ import annotations

import uuid

from api.application.contracts import ActionOutcomeFeedback, ActionOutcomeFeedbackRecord, ActionOutcomeRecord
from api.application.action_outcome_scoring import ActionOutcomeScoreCalculator
from api.application.ports.action_outcomes import ActionOutcomeMemoryPort


class ActionOutcomeRecorder:
    """Coordinates outcome measurement, scoring policy, and persistence."""

    def __init__(
        self,
        store: ActionOutcomeMemoryPort,
        score_calculator: type[ActionOutcomeScoreCalculator] = ActionOutcomeScoreCalculator,
    ) -> None:
        self.store = store
        self.score_calculator = score_calculator

    async def record_finished_run(self, *, run_id: uuid.UUID) -> ActionOutcomeRecord | None:
        draft = await self.store.load_run_outcome_draft(run_id=run_id)
        if draft is None:
            return None
        score = self.score_calculator.calculate(
            measures=draft.measures,
            status=draft.status,
            terminal_outcome=draft.terminal_outcome,
        )
        return await self.store.upsert_run_outcome(draft=draft, score=score)

    async def apply_feedback(
        self,
        *,
        action_id: uuid.UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord | None:
        return await self.store.apply_feedback(action_id=action_id, feedback=feedback)
