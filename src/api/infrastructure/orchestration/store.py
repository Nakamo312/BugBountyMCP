"""SQLAlchemy persistence for action, job, run, and event state."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
    EventEnvelope,
    ExecutionMode,
    ExecutionStatus,
    NodeRunClaim,
    PolicyDecision,
    PolicyDecisionStatus,
    ScheduledNodeRun,
    TerminalOutcome,
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

    async def claim_node_run(
        self,
        *,
        claim_key: str,
        job_id: uuid.UUID,
        program_id: uuid.UUID,
        node_id: str,
        event_name: str,
        trigger_event_id: uuid.UUID,
        input_fingerprint: str,
        target_fingerprint: str,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
    ) -> NodeRunClaim:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            existing = await self._select_node_run_claim(session, claim_key)
            if existing is not None:
                return existing

            run_id = uuid.uuid4()
            try:
                await session.execute(
                    insert(runs).values(
                        id=run_id,
                        job_id=job_id,
                        program_id=program_id,
                        node_id=node_id,
                        event_name=event_name,
                        trigger_event_id=trigger_event_id,
                        claim_key=claim_key,
                        input_fingerprint=input_fingerprint,
                        target_fingerprint=target_fingerprint,
                        execution_mode=execution_mode.value,
                        status=ExecutionStatus.QUEUED.value,
                        attempt=1,
                        needs_reconcile=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.commit()
                return NodeRunClaim(
                    run_id=run_id,
                    claim_key=claim_key,
                    status=ExecutionStatus.QUEUED,
                )
            except IntegrityError:
                await session.rollback()
                existing = await self._select_node_run_claim(session, claim_key)
                if existing is not None:
                    return existing
                raise

    async def lease_scheduled_node_runs(
        self,
        *,
        limit: int = 10,
    ) -> list[ScheduledNodeRun]:
        if limit <= 0:
            return []

        now = datetime.now(timezone.utc)
        query = (
            select(
                runs.c.id.label("run_id"),
                runs.c.node_id,
                runs.c.job_id,
                runs.c.program_id,
                runs.c.trigger_event_id,
                event_store.c.event_type,
                event_store.c.correlation_id,
                event_store.c.causation_id,
                event_store.c.source,
                event_store.c.profile,
                event_store.c.confidence,
                event_store.c.payload,
            )
            .select_from(
                runs.join(
                    event_store,
                    runs.c.trigger_event_id == event_store.c.event_id,
                )
            )
            .where(
                runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                runs.c.status == ExecutionStatus.QUEUED.value,
                runs.c.terminal_outcome.is_(None),
                runs.c.needs_reconcile.is_(False),
            )
            .order_by(runs.c.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True, of=runs)
        )

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
            if not rows:
                await session.commit()
                return []

            run_ids = [row["run_id"] for row in rows]
            await session.execute(
                update(runs)
                .where(runs.c.id.in_(run_ids))
                .values(
                    status=ExecutionStatus.RUNNING.value,
                    scanner_started_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        return [self._scheduled_node_run_from_row(row) for row in rows]

    async def mark_run_finished(
        self,
        *,
        run_id: uuid.UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> None:
        if status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }:
            raise ValueError(f"Invalid terminal run status: {status}")

        now = datetime.now(timezone.utc)
        retry_values = self._retry_values(
            now=now,
            status=status,
            terminal_outcome=terminal_outcome,
            retry_policy=retry_policy,
        )
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    status=status.value,
                    finished_at=now,
                    updated_at=now,
                    error=error,
                    terminal_outcome=(
                        terminal_outcome.value if terminal_outcome is not None else None
                    ),
                    **retry_values,
                )
            )
            await session.commit()

    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
    ) -> int:
        now = datetime.now(timezone.utc)
        requeued = 0

        async with self.session_factory() as session:
            for node_id, policy in retry_policies.items():
                max_attempts = int(policy.get("max_attempts", 1))
                terminal_outcomes = list(policy.get("terminal_outcomes") or [])
                if max_attempts <= 1 or not terminal_outcomes:
                    continue

                result = await session.execute(
                    select(runs.c.id)
                    .where(
                        runs.c.node_id == node_id,
                        runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                        runs.c.status == ExecutionStatus.FAILED.value,
                        runs.c.terminal_outcome.in_(terminal_outcomes),
                        runs.c.attempt < max_attempts,
                        runs.c.needs_reconcile.is_(False),
                        or_(
                            runs.c.next_retry_at.is_(None),
                            runs.c.next_retry_at <= now,
                        ),
                    )
                    .order_by(runs.c.updated_at.asc())
                )
                run_ids = [
                    row["id"] if isinstance(row, dict) else row[0]
                    for row in result.all()
                ]
                if not run_ids:
                    continue

                await session.execute(
                    update(runs)
                    .where(runs.c.id.in_(run_ids))
                    .values(
                        status=ExecutionStatus.QUEUED.value,
                        attempt=runs.c.attempt + 1,
                        started_at=None,
                        scanner_started_at=None,
                        finished_at=None,
                        terminal_outcome=None,
                        error=None,
                        next_retry_at=None,
                        retry_reason=terminal_outcomes[0],
                        updated_at=now,
                    )
                )
                requeued += len(run_ids)

            await session.commit()

        return requeued

    async def mark_run_needs_reconcile(
        self,
        *,
        run_id: uuid.UUID,
        reason: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    needs_reconcile=True,
                    reconcile_reason=reason,
                    updated_at=now,
                )
            )
            await session.commit()

    async def clear_run_reconcile(
        self,
        *,
        run_id: uuid.UUID,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    needs_reconcile=False,
                    reconcile_reason=None,
                    updated_at=now,
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

    @staticmethod
    async def _select_node_run_claim(session, claim_key: str) -> NodeRunClaim | None:
        result = await session.execute(
            select(
                runs.c.id,
                runs.c.claim_key,
                runs.c.status,
                runs.c.terminal_outcome,
            ).where(runs.c.claim_key == claim_key)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None

        terminal_outcome = (
            TerminalOutcome(row["terminal_outcome"])
            if row["terminal_outcome"] is not None
            else None
        )
        return NodeRunClaim(
            run_id=row["id"],
            claim_key=row["claim_key"],
            status=ExecutionStatus(row["status"]),
            terminal_outcome=terminal_outcome,
        )

    @staticmethod
    def _retry_values(
        *,
        now: datetime,
        status: ExecutionStatus,
        terminal_outcome: TerminalOutcome | None,
        retry_policy: dict | None,
    ) -> dict:
        if (
            status != ExecutionStatus.FAILED
            or terminal_outcome is None
            or not retry_policy
        ):
            return {"next_retry_at": None}

        terminal_outcomes = set(retry_policy.get("terminal_outcomes") or [])
        max_attempts = int(retry_policy.get("max_attempts", 1))
        if terminal_outcome.value not in terminal_outcomes or max_attempts <= 1:
            return {"next_retry_at": None}

        backoff_seconds = float(retry_policy.get("backoff_seconds", 0) or 0)
        return {
            "next_retry_at": now + timedelta(seconds=max(0, backoff_seconds)),
            "retry_reason": terminal_outcome.value,
        }

    @staticmethod
    def _scheduled_node_run_from_row(row) -> ScheduledNodeRun:
        event = dict(row["payload"] or {})
        event.update(
            {
                "event": row["event_type"],
                "event_id": str(row["trigger_event_id"]),
                "job_id": str(row["job_id"]),
                "program_id": str(row["program_id"]),
                "run_id": str(row["run_id"]),
                "correlation_id": str(row["correlation_id"]),
                "source": row["source"],
                "confidence": row["confidence"],
            }
        )
        if row["causation_id"] is not None:
            event["causation_id"] = str(row["causation_id"])
        if row["profile"] is not None:
            event["profile"] = row["profile"]

        return ScheduledNodeRun(
            run_id=row["run_id"],
            node_id=row["node_id"],
            event=event,
        )
