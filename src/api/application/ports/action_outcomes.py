"""Ports for action outcome memory persistence."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from api.application.contracts import (
    ActionOutcomeDraft,
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionOutcomeRecord,
    ActionOutcomeScore,
)


class ActionOutcomeMemoryPort(Protocol):
    """Persistence boundary required by ActionOutcomeRecorder."""

    async def load_run_outcome_draft(self, *, run_id: UUID) -> ActionOutcomeDraft | None:
        ...

    async def upsert_run_outcome(
        self,
        *,
        draft: ActionOutcomeDraft,
        score: ActionOutcomeScore,
    ) -> ActionOutcomeRecord:
        ...

    async def apply_feedback(
        self,
        *,
        action_id: UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord | None:
        ...
