"""Session boundary for action outcome memory persistence."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionOutcomeDraft,
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionOutcomeRecord,
    ActionOutcomeScore,
)
from api.infrastructure.action_outcome_feedback import apply_action_outcome_feedback_in_session
from api.infrastructure.action_outcome_mappers import draft_from_run_context
from api.infrastructure.action_outcome_measures import collect_action_outcome_measures
from api.infrastructure.action_outcome_persistence import upsert_action_outcome_in_session
from api.infrastructure.action_outcome_queries import run_context_query


class ActionOutcomeStore:
    """Run-scoped persistence for measured action outcomes."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def load_run_outcome_draft(self, *, run_id: uuid.UUID) -> ActionOutcomeDraft | None:
        async with self.session_factory() as session:
            context_result = await session.execute(run_context_query(run_id))
            row = context_result.mappings().one_or_none()
            if row is None:
                return None
            measures = await collect_action_outcome_measures(session, run_id=run_id, row=row)
            return draft_from_run_context(row=row, measures=measures)

    async def upsert_run_outcome(
        self,
        *,
        draft: ActionOutcomeDraft,
        score: ActionOutcomeScore,
    ) -> ActionOutcomeRecord:
        async with self.session_factory() as session:
            record = await upsert_action_outcome_in_session(
                session,
                draft=draft,
                score=score,
                now=datetime.now(timezone.utc),
            )
            await session.commit()
            return record

    async def apply_feedback(
        self,
        *,
        action_id: uuid.UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord | None:
        async with self.session_factory() as session:
            record = await apply_action_outcome_feedback_in_session(
                session,
                action_id=action_id,
                feedback=feedback,
                now=datetime.now(timezone.utc),
            )
            if record is not None:
                await session.commit()
            return record
