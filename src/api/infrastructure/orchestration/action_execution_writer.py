"""Atomic inserts for queued action execution records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert

from api.application.contracts import EventEnvelope, ExecutionStatus, ResolvedActionCommand
from api.infrastructure.adapters.orm import jobs, runs
from api.infrastructure.orchestration.event_store import insert_event_store_row


def run_payload_for_action(action: ResolvedActionCommand) -> dict[str, Any]:
    return {
        "options": dict(action.profile.options),
        "execution_budget": action.effective_budget.model_dump(mode="json"),
    }


async def insert_queued_execution(
    session,
    *,
    action: ResolvedActionCommand,
    envelope: EventEnvelope,
    now: datetime,
) -> None:
    """Insert job, run, and event-store rows in the caller's transaction."""
    await session.execute(
        insert(jobs).values(
            id=envelope.job_id,
            action_id=action.action_id,
            program_id=action.program_id,
            capability_id=action.profile.capability_id,
            profile_id=action.profile.profile_id,
            status=ExecutionStatus.QUEUED.value,
            correlation_id=envelope.correlation_id,
            campaign_id=action.campaign_id,
            created_at=now,
            updated_at=now,
        )
    )
    await session.execute(
        insert(runs).values(
            id=envelope.run_id,
            job_id=envelope.job_id,
            program_id=action.program_id,
            event_name=envelope.event,
            trigger_event_id=envelope.event_id,
            status=ExecutionStatus.QUEUED.value,
            attempt=1,
            run_payload=run_payload_for_action(action),
            created_at=now,
            updated_at=now,
        )
    )
    await insert_event_store_row(session, envelope)
