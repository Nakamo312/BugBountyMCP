"""SQLAlchemy persistence for action, job, run, and event state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
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

    async def list_actions(
        self,
        *,
        status: str | None = None,
        program_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        query = select(action_requests).order_by(action_requests.c.created_at.desc())
        if status is not None:
            query = query.where(action_requests.c.status == status)
        if program_id is not None:
            query = query.where(action_requests.c.program_id == program_id)
        query = query.limit(limit).offset(offset)

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()

        records: list[ActionRecord] = []
        for row in rows:
            request = ActionRequest.model_validate(row["request"])
            records.append(
                ActionRecord(
                    action_id=row["id"],
                    program_id=row["program_id"],
                    kind=ActionKind(row["kind"]),
                    capability_id=row["capability_id"],
                    profile_id=row["profile_id"],
                    requested_by=row["requested_by"],
                    status=ActionStatus(row["status"]),
                    targets=request.profile.targets,
                    options=request.profile.options,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return records

    async def get_action_for_approval(
        self,
        action_id: uuid.UUID,
    ) -> tuple[ActionRequest | None, str | None]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    action_requests.c.request,
                    action_requests.c.status,
                ).where(action_requests.c.id == action_id)
            )
            row = result.mappings().one_or_none()

        if row is None:
            return None, None
        return ActionRequest.model_validate(row["request"]), row["status"]

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
                update(action_requests)
                .where(action_requests.c.id == action.action_id)
                .values(
                    status="queued",
                    updated_at=now,
                )
            )
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
                    event_name=envelope.event,
                    trigger_event_id=envelope.event_id,
                    status=ExecutionStatus.QUEUED.value,
                    attempt=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

    async def approve_and_create_queued_job(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
        envelope: EventEnvelope,
    ) -> bool:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            transition = await session.execute(
                update(action_requests)
                .where(
                    action_requests.c.id == action.action_id,
                    action_requests.c.status == "requires_approval",
                )
                .values(
                    status="queued",
                    updated_at=now,
                )
            )
            if transition.rowcount != 1:
                await session.rollback()
                return False
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
                    event_name=envelope.event,
                    trigger_event_id=envelope.event_id,
                    status=ExecutionStatus.QUEUED.value,
                    attempt=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return True

    async def mark_run_started(
        self,
        *,
        run_id: uuid.UUID,
        node_id: str,
        event_name: str | None,
        trigger_event_id: uuid.UUID | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        values = {
            "node_id": node_id,
            "event_name": event_name,
            "trigger_event_id": trigger_event_id,
            "status": ExecutionStatus.RUNNING.value,
            "started_at": now,
            "updated_at": now,
            "error": None,
        }
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(**values)
            )
            await session.commit()

    async def mark_run_finished(
        self,
        *,
        run_id: uuid.UUID,
        status: ExecutionStatus,
        error: str | None = None,
    ) -> None:
        if status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }:
            raise ValueError(f"Invalid terminal run status: {status}")

        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    status=status.value,
                    finished_at=now,
                    updated_at=now,
                    error=error,
                )
            )
            await session.commit()

    async def reject_action(
        self,
        action: ActionRequest,
        decision: PolicyDecision,
    ) -> bool:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            transition = await session.execute(
                update(action_requests)
                .where(
                    action_requests.c.id == action.action_id,
                    action_requests.c.status == "requires_approval",
                )
                .values(
                    status="rejected",
                    updated_at=now,
                )
            )
            if transition.rowcount != 1:
                await session.rollback()
                return False
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
            return True

    async def record_event(self, envelope: EventEnvelope) -> None:
        payload = envelope.to_legacy_dict()
        payload.pop("event_id", None)
        payload.pop("created_at", None)

        async with self.session_factory() as session:
            try:
                await self._ensure_run_for_event(session, envelope)
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

    @staticmethod
    async def _ensure_run_for_event(session, envelope: EventEnvelope) -> None:
        result = await session.execute(
            select(runs.c.id).where(runs.c.id == envelope.run_id)
        )
        if result.one_or_none() is not None:
            return

        now = datetime.now(timezone.utc)
        await session.execute(
            insert(runs).values(
                id=envelope.run_id,
                job_id=envelope.job_id,
                program_id=envelope.program_id,
                event_name=envelope.event,
                trigger_event_id=envelope.causation_id or envelope.event_id,
                status=ExecutionStatus.QUEUED.value,
                attempt=1,
                created_at=now,
                updated_at=now,
            )
        )
