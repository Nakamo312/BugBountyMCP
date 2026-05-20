"""SQLAlchemy persistence for action, job, run, and event state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionRequest,
    EventEnvelope,
    ExecutionStatus,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.infrastructure.adapters.orm import (
    action_requests,
    event_store,
    jobs,
    policy_decisions,
    runs,
)


class OrchestrationStore:
    """Durable write model for orchestration state."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def record_policy_result(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
    ) -> None:
        now = datetime.now(timezone.utc)
        status = (
            "queued"
            if decision.status == PolicyDecisionStatus.ALLOWED
            else decision.status.value
        )

        async with self.session_factory() as session:
            await session.execute(
                insert(action_requests).values(
                    id=action.action_id,
                    program_id=action.program_id,
                    kind=action.kind.value,
                    capability_id=action.profile.capability_id,
                    profile_id=action.profile.profile_id,
                    requested_by=action.requested_by,
                    status=status,
                    request=action.model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                insert(policy_decisions).values(
                    id=decision.decision_id,
                    action_id=action.action_id,
                    status=decision.status.value,
                    reasons=decision.reasons,
                    allowed_targets=decision.allowed_targets,
                    blocked_targets=decision.blocked_targets,
                    created_at=now,
                )
            )
            await session.commit()

    async def create_queued_job(
        self,
        action: ActionRequest,
        envelope: EventEnvelope,
    ) -> None:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            await session.execute(
                insert(jobs).values(
                    id=envelope.job_id,
                    action_id=action.action_id,
                    program_id=action.program_id,
                    capability_id=action.profile.capability_id,
                    profile_id=action.profile.profile_id,
                    status=ExecutionStatus.QUEUED.value,
                    correlation_id=envelope.correlation_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                insert(runs).values(
                    id=envelope.run_id,
                    job_id=envelope.job_id,
                    program_id=action.program_id,
                    status=ExecutionStatus.QUEUED.value,
                    attempt=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

    async def record_event(self, envelope: EventEnvelope) -> None:
        payload = envelope.to_legacy_dict()
        payload.pop("event_id", None)
        payload.pop("created_at", None)

        async with self.session_factory() as session:
            try:
                await session.execute(
                    insert(event_store).values(
                        id=uuid.uuid4(),
                        event_id=envelope.event_id,
                        event_type=envelope.event,
                        program_id=envelope.program_id,
                        job_id=envelope.job_id,
                        run_id=envelope.run_id,
                        correlation_id=envelope.correlation_id,
                        causation_id=envelope.causation_id,
                        source=envelope.source,
                        profile=envelope.profile,
                        confidence=envelope.confidence,
                        payload=payload,
                        created_at=envelope.created_at,
                    )
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
