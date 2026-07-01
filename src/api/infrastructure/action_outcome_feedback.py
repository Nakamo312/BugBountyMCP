"""Feedback audit transactions for action outcome memory."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import insert, update

from api.application.contracts import ActionOutcomeFeedback, ActionOutcomeFeedbackRecord
from api.infrastructure.action_outcome_mappers import action_outcome_record_from_row
from api.infrastructure.action_outcome_queries import action_outcome_by_id_query, feedback_target_query
from api.infrastructure.adapters.orm import action_outcome_feedback_events, action_outcomes


def feedback_update_values(
    *,
    feedback: ActionOutcomeFeedback,
    now: datetime,
) -> dict[str, Any]:
    values: dict[str, Any] = {"updated_at": now}
    for field in (
        "manual_interest",
        "manual_stop",
        "continued_by_followup",
        "report_created",
        "triage_outcome",
    ):
        value = getattr(feedback, field)
        if value is not None:
            values[field] = value
    return values


def feedback_event_values(
    *,
    row: Mapping[str, Any],
    feedback_id: uuid.UUID,
    feedback: ActionOutcomeFeedback,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": feedback_id,
        "outcome_id": row["outcome_id"],
        "program_id": row["program_id"],
        "campaign_id": row.get("campaign_id"),
        "action_id": row["action_id"],
        "job_id": row["job_id"],
        "run_id": row["run_id"],
        "manual_interest": feedback.manual_interest,
        "manual_stop": feedback.manual_stop,
        "continued_by_followup": feedback.continued_by_followup,
        "report_created": feedback.report_created,
        "triage_outcome": feedback.triage_outcome,
        "actor": feedback.actor,
        "source": feedback.source,
        "reason": feedback.reason,
        "confidence": feedback.confidence,
        "created_at": now,
    }


async def apply_action_outcome_feedback_in_session(
    session,
    *,
    action_id: uuid.UUID,
    feedback: ActionOutcomeFeedback,
    now: datetime,
) -> ActionOutcomeFeedbackRecord | None:
    target_result = await session.execute(
        feedback_target_query(action_id=action_id, run_id=feedback.run_id)
    )
    row = target_result.mappings().one_or_none()
    if row is None:
        return None

    event_id = uuid.uuid4()
    await session.execute(
        insert(action_outcome_feedback_events).values(
            feedback_event_values(
                row=row,
                feedback_id=event_id,
                feedback=feedback,
                now=now,
            )
        )
    )
    updates = feedback_update_values(feedback=feedback, now=now)
    if updates:
        await session.execute(
            update(action_outcomes)
            .where(action_outcomes.c.id == row["outcome_id"])
            .values(**updates)
        )
    refreshed_result = await session.execute(action_outcome_by_id_query(row["outcome_id"]))
    refreshed = refreshed_result.mappings().one()
    outcome = action_outcome_record_from_row(refreshed)
    return ActionOutcomeFeedbackRecord(
        feedback_id=event_id,
        outcome_id=row["outcome_id"],
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        action_id=row["action_id"],
        job_id=row["job_id"],
        run_id=row["run_id"],
        manual_interest=feedback.manual_interest,
        manual_stop=feedback.manual_stop,
        continued_by_followup=feedback.continued_by_followup,
        report_created=feedback.report_created,
        triage_outcome=feedback.triage_outcome,
        actor=feedback.actor,
        source=feedback.source,
        reason=feedback.reason,
        confidence=feedback.confidence,
        created_at=now,
        outcome=outcome,
    )
