"""Write transaction helpers for action outcome memory."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.application.contracts import ActionOutcomeDraft, ActionOutcomeRecord, ActionOutcomeScore
from api.infrastructure.action_outcome_mappers import (
    action_outcome_record_from_values,
    values_from_run_context,
)
from api.infrastructure.adapters.orm import action_outcomes


async def upsert_action_outcome_in_session(
    session,
    *,
    draft: ActionOutcomeDraft,
    score: ActionOutcomeScore,
    now: datetime,
) -> ActionOutcomeRecord:
    values = values_from_run_context(
        row=draft.row,
        outcome_id=draft.outcome_id,
        measures=draft.measures,
        score=score,
        now=now,
    )
    stmt = pg_insert(action_outcomes).values(values)
    update_values = {
        key: value
        for key, value in values.items()
        if key not in {"id", "run_id", "created_at"}
    }
    update_values["updated_at"] = now
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[action_outcomes.c.run_id],
            set_=update_values,
        )
    )
    return action_outcome_record_from_values(
        values={**values, "updated_at": now},
        measures=draft.measures,
        score=score,
    )
