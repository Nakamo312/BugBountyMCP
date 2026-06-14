"""SQLAlchemy persistence for action, job, run, and event state."""
from __future__ import annotations

import json
import random
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, insert, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionStatus,
    EventDispatchRecord,
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
    action_request_options,
    action_request_targets,
    action_requests,
    approval_decisions,
    approval_requests,
    campaigns,
    event_dispatches,
    event_store,
    jobs,
    policy_decisions,
    runs,
    scope_decisions,
)
from api.infrastructure.events.queue_config import QueueConfig


class OrchestrationStore:
    """Durable write model for orchestration state."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    @staticmethod
    def _scope_status(decision: PolicyDecision) -> str:
        if decision.status == PolicyDecisionStatus.BLOCKED:
            return "blocked"
        if decision.allowed_targets and decision.blocked_targets:
            return "partial"
        if decision.allowed_targets:
            return "allowed"
        return "not_evaluated"

    @staticmethod
    def _event_store_payload(envelope: EventEnvelope) -> dict[str, Any]:
        payload = envelope.to_legacy_dict()
        payload.pop("event_id", None)
        payload.pop("created_at", None)
        return payload

    @staticmethod
    async def _insert_event_store_row(session, envelope: EventEnvelope) -> None:
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
                payload=OrchestrationStore._event_store_payload(envelope),
                created_at=envelope.created_at,
            )
        )

    @staticmethod
    async def _enqueue_dispatch(
        session,
        envelope: EventEnvelope,
        *,
        destination: str = "rabbitmq",
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        await session.execute(
            insert(event_dispatches).values(
                id=uuid.uuid4(),
                event_id=envelope.event_id,
                destination=destination,
                routing_key=QueueConfig.get_routing_key(envelope.event),
                status="pending",
                attempts=0,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        await session.execute(
            text("SELECT pg_notify(:channel, :payload)").bindparams(
                channel="event_dispatches_changed",
                payload=str(envelope.event_id),
            )
        )

    @staticmethod
    def _event_envelope_from_event_store_row(row: Mapping[str, Any]) -> EventEnvelope:
        payload = dict(row.get("payload") or {})
        payload.update(
            {
                "event_id": row["event_id"],
                "event": row["event_type"],
                "program_id": row["program_id"],
                "correlation_id": row["correlation_id"],
                "causation_id": row.get("causation_id"),
                "source": row["source"],
                "profile": row.get("profile"),
                "confidence": row["confidence"],
                "created_at": row["event_created_at"],
            }
        )
        if row.get("job_id") is not None:
            payload["job_id"] = row["job_id"]
        if row.get("run_id") is not None:
            payload["run_id"] = row["run_id"]
        return EventEnvelope(**payload)

    async def claim_dispatches(
        self,
        *,
        destination: str,
        dispatcher_id: str,
        batch_size: int,
        lease_ttl_seconds: int,
    ) -> list[EventDispatchRecord]:
        now = datetime.now(timezone.utc)
        locked_until = now + timedelta(seconds=max(1, lease_ttl_seconds))
        limit = max(1, batch_size)

        pending_or_failed = (
            event_dispatches.c.status.in_(["pending", "failed"])
            & (event_dispatches.c.available_at <= now)
        )
        expired_lock = (
            (event_dispatches.c.status == "locked")
            & (event_dispatches.c.locked_until.is_not(None))
            & (event_dispatches.c.locked_until <= now)
        )

        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    event_dispatches.c.id.label("dispatch_id"),
                    event_dispatches.c.event_id,
                    event_dispatches.c.destination,
                    event_dispatches.c.routing_key,
                    event_dispatches.c.attempts,
                    event_store.c.event_type,
                    event_store.c.program_id,
                    event_store.c.job_id,
                    event_store.c.run_id,
                    event_store.c.correlation_id,
                    event_store.c.causation_id,
                    event_store.c.source,
                    event_store.c.profile,
                    event_store.c.confidence,
                    event_store.c.payload,
                    event_store.c.created_at.label("event_created_at"),
                )
                .select_from(
                    event_dispatches.join(
                        event_store,
                        event_dispatches.c.event_id == event_store.c.event_id,
                    )
                )
                .where(
                    event_dispatches.c.destination == destination,
                    or_(pending_or_failed, expired_lock),
                )
                .order_by(event_dispatches.c.available_at.asc(), event_dispatches.c.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True, of=event_dispatches)
            )
            rows = result.mappings().all()
            if not rows:
                await session.commit()
                return []

            dispatch_ids = [row["dispatch_id"] for row in rows]
            await session.execute(
                update(event_dispatches)
                .where(event_dispatches.c.id.in_(dispatch_ids))
                .values(
                    status="locked",
                    locked_by=dispatcher_id,
                    locked_until=locked_until,
                    updated_at=now,
                )
            )
            await session.commit()

        return [
            EventDispatchRecord(
                dispatch_id=row["dispatch_id"],
                event_id=row["event_id"],
                destination=row["destination"],
                routing_key=row["routing_key"],
                attempts=int(row["attempts"] or 0),
                envelope=self._event_envelope_from_event_store_row(row),
            )
            for row in rows
        ]

    async def mark_sent(
        self,
        *,
        dispatch_id: uuid.UUID,
        dispatcher_id: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                update(event_dispatches)
                .where(
                    event_dispatches.c.id == dispatch_id,
                    event_dispatches.c.locked_by == dispatcher_id,
                )
                .values(
                    status="dispatched",
                    dispatched_at=now,
                    locked_by=None,
                    locked_until=None,
                    updated_at=now,
                )
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def mark_failed(
        self,
        *,
        dispatch_id: uuid.UUID,
        dispatcher_id: str,
        error: str,
        current_attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> bool:
        now = datetime.now(timezone.utc)
        next_attempts = max(0, int(current_attempts)) + 1
        status = "dead" if next_attempts >= max(1, int(max_attempts)) else "failed"
        available_at = now if status == "dead" else now + timedelta(seconds=max(0.1, retry_delay_seconds))
        async with self.session_factory() as session:
            result = await session.execute(
                update(event_dispatches)
                .where(
                    event_dispatches.c.id == dispatch_id,
                    event_dispatches.c.locked_by == dispatcher_id,
                )
                .values(
                    status=status,
                    attempts=next_attempts,
                    available_at=available_at,
                    locked_by=None,
                    locked_until=None,
                    last_error=error[:4000],
                    updated_at=now,
                )
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    @staticmethod
    def _target_status(target: str, decision: PolicyDecision) -> str:
        if target in decision.allowed_targets:
            return "allowed"
        if target in decision.blocked_targets:
            return "blocked"
        return "requested"

    @staticmethod
    def _catalog_hash(decision: PolicyDecision) -> str | None:
        value = decision.metadata.get("catalog_hash")
        return str(value) if value else None

    async def _upsert_campaign(self, session, action: ActionRequest, now: datetime) -> None:
        stmt = pg_insert(campaigns).values(
            id=action.campaign_id,
            program_id=action.program_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            status="created",
            metadata=action.metadata,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[campaigns.c.id],
            set_={
                "updated_at": now,
                "correlation_id": action.correlation_id,
                "workflow_id": action.workflow_id,
            },
        )
        await session.execute(stmt)

    async def _record_action_detail_rows(
        self,
        session,
        *,
        action: ActionRequest,
        decision: PolicyDecision,
        now: datetime,
    ) -> uuid.UUID:
        for position, target in enumerate(action.profile.targets):
            await session.execute(
                insert(action_request_targets).values(
                    id=uuid.uuid4(),
                    action_id=action.action_id,
                    target=target,
                    position=position,
                    status=self._target_status(target, decision),
                    created_at=now,
                )
            )
        for key, value in sorted(action.profile.options.items()):
            await session.execute(
                insert(action_request_options).values(
                    id=uuid.uuid4(),
                    action_id=action.action_id,
                    option_key=key,
                    option_value=value,
                    created_at=now,
                )
            )
        scope_decision_id = uuid.uuid4()
        await session.execute(
            insert(scope_decisions).values(
                id=scope_decision_id,
                action_id=action.action_id,
                status=self._scope_status(decision),
                scope_policy=decision.metadata.get("scope_policy"),
                reasons=decision.reasons,
                allowed_targets=decision.allowed_targets,
                blocked_targets=decision.blocked_targets,
                metadata=decision.metadata,
                created_at=now,
            )
        )
        return scope_decision_id

    async def _record_approval_request_if_needed(
        self,
        session,
        *,
        action: ActionRequest,
        decision: PolicyDecision,
        now: datetime,
    ) -> None:
        if decision.status != PolicyDecisionStatus.REQUIRES_APPROVAL:
            return
        await session.execute(
            insert(approval_requests).values(
                id=uuid.uuid4(),
                action_id=action.action_id,
                policy_decision_id=decision.decision_id,
                status="pending",
                reason="; ".join(decision.reasons) if decision.reasons else None,
                requested_by="policy",
                created_at=now,
            )
        )

    async def _record_approval_decision(
        self,
        session,
        *,
        action: ActionRequest,
        decision: PolicyDecision,
        status: str,
        decided_by: str,
        reason: str | None,
        now: datetime,
    ) -> None:
        pending = await session.execute(
            select(approval_requests.c.id)
            .where(
                approval_requests.c.action_id == action.action_id,
                approval_requests.c.status == "pending",
            )
            .order_by(approval_requests.c.created_at.desc())
            .limit(1)
        )
        row = pending.mappings().one_or_none()
        approval_request_id = row["id"] if row else uuid.uuid4()
        if row is None:
            await session.execute(
                insert(approval_requests).values(
                    id=approval_request_id,
                    action_id=action.action_id,
                    policy_decision_id=decision.decision_id,
                    status=status,
                    reason=reason,
                    requested_by="policy",
                    created_at=now,
                    decided_at=now,
                )
            )
        else:
            await session.execute(
                update(approval_requests)
                .where(approval_requests.c.id == approval_request_id)
                .values(status=status, decided_at=now, reason=reason)
            )
        await session.execute(
            insert(approval_decisions).values(
                id=uuid.uuid4(),
                approval_request_id=approval_request_id,
                action_id=action.action_id,
                decision=status,
                decided_by=decided_by,
                reason=reason,
                metadata=decision.metadata,
                created_at=now,
            )
        )

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
                    targets=request.targets,
                    options=request.options,
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
    ) -> uuid.UUID:
        now = datetime.now(timezone.utc)
        status = (
            "queued"
            if decision.status == PolicyDecisionStatus.ALLOWED
            else decision.status.value
        )

        async with self.session_factory() as session:
            await self._upsert_campaign(session, action, now)
            await session.execute(
                insert(action_requests).values(
                    id=action.action_id,
                    program_id=action.program_id,
                    catalog_entry_id=action.catalog_id,
                    kind=action.kind.value,
                    capability_id=action.profile.capability_id,
                    profile_id=action.profile.profile_id,
                    requested_by=action.requested_by,
                    workflow_id=action.workflow_id,
                    campaign_id=action.campaign_id,
                    correlation_id=action.correlation_id,
                    catalog_hash=self._catalog_hash(decision),
                    metadata=action.metadata,
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
                    safety_level=decision.safety_level.value if decision.safety_level is not None else None,
                    metadata=decision.metadata,
                    catalog_hash=self._catalog_hash(decision),
                    created_at=now,
                )
            )
            scope_id = await self._record_action_detail_rows(
                session,
                action=action,
                decision=decision,
                now=now,
            )
            await self._record_approval_request_if_needed(
                session,
                action=action,
                decision=decision,
                now=now,
            )
            await session.commit()
        return scope_id

    async def get_scope_id(self, action_id: uuid.UUID) -> uuid.UUID | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(scope_decisions.c.id)
                .where(scope_decisions.c.action_id == action_id)
                .order_by(scope_decisions.c.created_at.desc())
                .limit(1)
            )
            row = result.mappings().one_or_none()
        return row["id"] if row else None

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
                    created_at=now,
                    updated_at=now,
                )
            )
            await self._insert_event_store_row(session, envelope)
            await self._enqueue_dispatch(session, envelope, now=now)
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
                    safety_level=decision.safety_level.value if decision.safety_level is not None else None,
                    metadata=decision.metadata,
                    catalog_hash=self._catalog_hash(decision),
                    created_at=now,
                )
            )
            await self._record_approval_decision(
                session,
                action=action,
                decision=decision,
                status="approved",
                decided_by=decision.metadata.get("approved_by", "api"),
                reason="; ".join(decision.reasons) if decision.reasons else None,
                now=now,
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
                    created_at=now,
                    updated_at=now,
                )
            )
            await self._insert_event_store_row(session, envelope)
            await self._enqueue_dispatch(session, envelope, now=now)
            await session.commit()
            return True

    async def mark_run_started(
        self,
        *,
        run_id: uuid.UUID,
        node_id: str,
        event_name: str | None,
        trigger_event_id: uuid.UUID | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        values = {
            "node_id": node_id,
            "event_name": event_name,
            "trigger_event_id": trigger_event_id,
            "status": ExecutionStatus.RUNNING.value,
            "started_at": now,
            "scanner_started_at": now,
            "leased_at": None,
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": now,
            "error": None,
        }

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(
                    or_(
                        runs.c.execution_mode != ExecutionMode.SCHEDULED.value,
                        runs.c.status == ExecutionStatus.LEASED.value,
                    )
                )
                .values(**values)
            )
            await session.commit()

        return int(getattr(result, "rowcount", 0) or 0) == 1

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
        next_run_at: datetime | None = None,
        target_count: int | None = None,
        run_payload: Mapping[str, Any] | None = None,
        work_key: str | None = None,
        coalesced_trigger: Mapping[str, Any] | None = None,
        retry_policy: dict | None = None,
    ) -> NodeRunClaim:
        now = datetime.now(timezone.utc)
        initial_coalesced_triggers = (
            [dict(coalesced_trigger)] if coalesced_trigger is not None else None
        )

        async with self.session_factory() as session:
            existing = await self._select_node_run_claim(session, claim_key)
            if existing is not None:
                return existing

            if execution_mode == ExecutionMode.SCHEDULED and work_key and retry_policy:
                existing_work = await self._select_retryable_failed_work_claim(
                    session,
                    work_key=work_key,
                    retry_policy=retry_policy,
                )
                if existing_work is not None:
                    await self._append_coalesced_trigger(
                        session,
                        run_id=existing_work["id"],
                        existing_triggers=existing_work.get("coalesced_triggers"),
                        coalesced_trigger=coalesced_trigger,
                        now=now,
                        reason=self._work_dedup_reason(existing_work.get("status")),
                    )
                    await session.commit()
                    return self._node_run_claim_from_row(existing_work)

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
                        work_key=work_key,
                        coalesced_triggers=initial_coalesced_triggers,
                        input_fingerprint=input_fingerprint,
                        target_fingerprint=target_fingerprint,
                        execution_mode=execution_mode.value,
                        status=ExecutionStatus.QUEUED.value,
                        attempt=1,
                        next_run_at=next_run_at,
                        target_count=target_count,
                        run_payload=dict(run_payload) if run_payload is not None else None,
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
                if execution_mode == ExecutionMode.SCHEDULED and work_key:
                    existing_work = await self._select_active_work_claim(
                        session,
                        work_key=work_key,
                    )
                    if existing_work is not None:
                        await self._append_coalesced_trigger(
                            session,
                            run_id=existing_work["id"],
                            existing_triggers=existing_work.get("coalesced_triggers"),
                            coalesced_trigger=coalesced_trigger,
                            now=now,
                            reason=self._work_dedup_reason(existing_work.get("status")),
                        )
                        await session.commit()
                        return self._node_run_claim_from_row(existing_work)
                raise

    async def count_scheduled_active_runs_by_node(self) -> dict[str, int]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    runs.c.node_id,
                    func.count().label("count"),
                )
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.status.in_(
                        [
                            ExecutionStatus.LEASED.value,
                            ExecutionStatus.RUNNING.value,
                            ExecutionStatus.FLUSHING.value,
                        ]
                    ),
                    runs.c.terminal_outcome.is_(None),
                    runs.c.needs_reconcile.is_(False),
                )
                .group_by(runs.c.node_id)
            )
            rows = result.mappings().all()

        return {
            row["node_id"]: int(row["count"] or 0)
            for row in rows
            if row["node_id"]
        }

    async def lease_ready_scheduled_node_runs(
        self,
        *,
        node_limits: Mapping[str, int],
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> list[ScheduledNodeRun]:
        positive_limits = {
            node_id: limit
            for node_id, limit in node_limits.items()
            if node_id and limit > 0
        }
        if not positive_limits:
            return []

        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=max(1, lease_ttl_seconds))
        leased_rows = []

        async with self.session_factory() as session:
            for node_id, limit in sorted(positive_limits.items()):
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
                        runs.c.run_payload,
                        runs.c.target_count,
                        runs.c.next_run_at,
                        runs.c.created_at,
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
                        runs.c.node_id == node_id,
                        runs.c.terminal_outcome.is_(None),
                        runs.c.needs_reconcile.is_(False),
                        or_(
                            runs.c.next_run_at.is_(None),
                            runs.c.next_run_at <= now,
                        ),
                    )
                    .order_by(runs.c.created_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=runs)
                )
                result = await session.execute(query)
                rows = result.mappings().all()
                if not rows:
                    continue

                leased_rows.extend(rows)

            if not leased_rows:
                await session.commit()
                return []

            leased_rows.sort(
                key=lambda row: (
                    row.get("next_run_at") or row.get("created_at") or now,
                    row.get("created_at") or now,
                    str(row["run_id"]),
                )
            )
            run_ids = [row["run_id"] for row in leased_rows]
            await session.execute(
                update(runs)
                .where(
                    runs.c.id.in_(run_ids),
                    runs.c.status == ExecutionStatus.QUEUED.value,
                )
                .values(
                    status=ExecutionStatus.LEASED.value,
                    leased_at=now,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                    updated_at=now,
                )
            )
            await session.commit()

        return [self._scheduled_node_run_from_row(row) for row in leased_rows]

    async def recover_stale_leases(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.status == ExecutionStatus.LEASED.value,
                    runs.c.lease_expires_at.is_not(None),
                    runs.c.lease_expires_at <= now,
                )
                .values(
                    status=ExecutionStatus.QUEUED.value,
                    leased_at=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    async def fail_stale_scheduled_active_runs(
        self,
        *,
        running_timeout_seconds: int,
        flushing_timeout_seconds: int,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        running_cutoff = now - timedelta(seconds=max(1, running_timeout_seconds))
        flushing_cutoff = now - timedelta(seconds=max(1, flushing_timeout_seconds))

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(
                    runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                    runs.c.terminal_outcome.is_(None),
                    runs.c.needs_reconcile.is_(False),
                    or_(
                        (
                            (runs.c.status == ExecutionStatus.RUNNING.value)
                            & (
                                or_(
                                    runs.c.started_at.is_(None),
                                    runs.c.started_at <= running_cutoff,
                                )
                            )
                        ),
                        (
                            (runs.c.status == ExecutionStatus.FLUSHING.value)
                            & (
                                or_(
                                    runs.c.flushing_at.is_(None),
                                    runs.c.flushing_at <= flushing_cutoff,
                                )
                            )
                        ),
                    ),
                )
                .values(
                    status=ExecutionStatus.FAILED.value,
                    terminal_outcome=TerminalOutcome.TOOL_FAILED.value,
                    error="Marked failed: stale scheduled active run exceeded timeout",
                    needs_reconcile=False,
                    reconcile_reason=None,
                    lease_owner=None,
                    leased_at=None,
                    lease_expires_at=None,
                    finished_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    async def mark_run_flushing(
        self,
        *,
        run_id: uuid.UUID,
    ) -> bool:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(
                    or_(
                        runs.c.execution_mode != ExecutionMode.SCHEDULED.value,
                        runs.c.status == ExecutionStatus.RUNNING.value,
                    )
                )
                .values(
                    status=ExecutionStatus.FLUSHING.value,
                    flushing_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def mark_run_finished(
        self,
        *,
        run_id: uuid.UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> bool:
        if status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.DEAD,
            ExecutionStatus.CANCELLED,
        }:
            raise ValueError(f"Invalid terminal run status: {status}")

        if status == ExecutionStatus.COMPLETED:
            allowed_source_statuses = [ExecutionStatus.FLUSHING.value]
        elif status == ExecutionStatus.FAILED:
            allowed_source_statuses = [
                ExecutionStatus.RUNNING.value,
                ExecutionStatus.FLUSHING.value,
            ]
        elif status == ExecutionStatus.DEAD:
            allowed_source_statuses = [ExecutionStatus.FAILED.value]
        elif status == ExecutionStatus.CANCELLED:
            allowed_source_statuses = [
                ExecutionStatus.QUEUED.value,
                ExecutionStatus.LEASED.value,
                ExecutionStatus.RUNNING.value,
                ExecutionStatus.FLUSHING.value,
            ]
        else:
            allowed_source_statuses = []

        now = datetime.now(timezone.utc)
        retry_values = self._retry_values(
            now=now,
            status=status,
            terminal_outcome=terminal_outcome,
            retry_policy=retry_policy,
        )

        async with self.session_factory() as session:
            result = await session.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .where(
                    or_(
                        runs.c.execution_mode != ExecutionMode.SCHEDULED.value,
                        runs.c.status.in_(allowed_source_statuses),
                    )
                )
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

        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
        max_requeues_per_node: int | None = None,
        retry_jitter_seconds: float = 0.0,
    ) -> int:
        now = datetime.now(timezone.utc)
        requeued = 0
        requeue_limit = int(max_requeues_per_node or 0)
        jitter_seconds = max(float(retry_jitter_seconds or 0.0), 0.0)

        async with self.session_factory() as session:
            for node_id, policy in retry_policies.items():
                max_attempts = int(policy.get("max_attempts", 1))
                terminal_outcomes = list(policy.get("terminal_outcomes") or [])
                if max_attempts <= 1 or not terminal_outcomes:
                    continue

                retry_query = (
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
                    .order_by(runs.c.updated_at.asc(), runs.c.id.asc())
                )
                if requeue_limit > 0:
                    retry_query = retry_query.limit(requeue_limit)

                result = await session.execute(retry_query)
                run_ids = [
                    row["id"] if isinstance(row, dict) else row[0]
                    for row in result.all()
                ]

                for run_id in run_ids:
                    next_run_at = None
                    if jitter_seconds > 0:
                        next_run_at = now + timedelta(
                            seconds=random.uniform(0.0, jitter_seconds)
                        )

                    await session.execute(
                        update(runs)
                        .where(runs.c.id == run_id)
                        .values(
                            status=ExecutionStatus.QUEUED.value,
                            attempt=runs.c.attempt + 1,
                            leased_at=None,
                            lease_owner=None,
                            lease_expires_at=None,
                            started_at=None,
                            scanner_started_at=None,
                            flushing_at=None,
                            finished_at=None,
                            terminal_outcome=None,
                            error=None,
                            next_retry_at=None,
                            next_run_at=next_run_at,
                            retry_reason=terminal_outcomes[0],
                            updated_at=now,
                        )
                    )

                requeued += len(run_ids)

                exhausted_result = await session.execute(
                    select(runs.c.id)
                    .where(
                        runs.c.node_id == node_id,
                        runs.c.execution_mode == ExecutionMode.SCHEDULED.value,
                        runs.c.status == ExecutionStatus.FAILED.value,
                        runs.c.terminal_outcome.in_(terminal_outcomes),
                        runs.c.attempt >= max_attempts,
                        runs.c.needs_reconcile.is_(False),
                        or_(
                            runs.c.next_retry_at.is_(None),
                            runs.c.next_retry_at <= now,
                        ),
                    )
                    .order_by(runs.c.updated_at.asc(), runs.c.id.asc())
                )
                exhausted_run_ids = [
                    row["id"] if isinstance(row, dict) else row[0]
                    for row in exhausted_result.all()
                ]
                if exhausted_run_ids:
                    await session.execute(
                        update(runs)
                        .where(runs.c.id.in_(exhausted_run_ids))
                        .values(
                            status=ExecutionStatus.DEAD.value,
                            next_retry_at=None,
                            retry_reason=terminal_outcomes[0],
                            updated_at=now,
                        )
                    )

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
                    safety_level=decision.safety_level.value if decision.safety_level is not None else None,
                    metadata=decision.metadata,
                    catalog_hash=self._catalog_hash(decision),
                    created_at=now,
                )
            )
            await self._record_approval_decision(
                session,
                action=action,
                decision=decision,
                status="rejected",
                decided_by=decision.metadata.get("rejected_by", "api"),
                reason="; ".join(decision.reasons) if decision.reasons else None,
                now=now,
            )
            await session.commit()
            return True

    async def record_event(self, envelope: EventEnvelope) -> None:
        async with self.session_factory() as session:
            try:
                await self._ensure_run_for_event(session, envelope)
                await self._insert_event_store_row(session, envelope)
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
    async def _select_active_work_claim(session, *, work_key: str):
        result = await session.execute(
            select(
                runs.c.id,
                runs.c.claim_key,
                runs.c.status,
                runs.c.terminal_outcome,
                runs.c.coalesced_triggers,
            )
            .where(runs.c.execution_mode == ExecutionMode.SCHEDULED.value)
            .where(runs.c.work_key == work_key)
            .where(
                runs.c.status.in_(
                    [
                        ExecutionStatus.QUEUED.value,
                        ExecutionStatus.LEASED.value,
                        ExecutionStatus.RUNNING.value,
                        ExecutionStatus.FLUSHING.value,
                    ]
                )
            )
            .where(runs.c.terminal_outcome.is_(None))
            .order_by(runs.c.created_at.asc())
        )
        return result.mappings().one_or_none()

    @staticmethod
    async def _select_retryable_failed_work_claim(
        session,
        *,
        work_key: str,
        retry_policy: dict,
    ):
        terminal_outcomes = list(retry_policy.get("terminal_outcomes") or [])
        max_attempts = int(retry_policy.get("max_attempts", 1) or 1)
        if not terminal_outcomes or max_attempts <= 1:
            return None

        result = await session.execute(
            select(
                runs.c.id,
                runs.c.claim_key,
                runs.c.status,
                runs.c.terminal_outcome,
                runs.c.coalesced_triggers,
            )
            .where(runs.c.execution_mode == ExecutionMode.SCHEDULED.value)
            .where(runs.c.work_key == work_key)
            .where(runs.c.status == ExecutionStatus.FAILED.value)
            .where(runs.c.terminal_outcome.in_(terminal_outcomes))
            .where(runs.c.attempt < max_attempts)
            .order_by(runs.c.updated_at.asc())
        )
        return result.mappings().one_or_none()

    @staticmethod
    def _work_dedup_reason(status: str | ExecutionStatus | None) -> str:
        status_value = status.value if isinstance(status, ExecutionStatus) else status

        if status_value == ExecutionStatus.QUEUED.value:
            return "queued_work_key"
        if status_value == ExecutionStatus.LEASED.value:
            return "leased_work_key"
        if status_value == ExecutionStatus.RUNNING.value:
            return "running_work_key"
        if status_value == ExecutionStatus.FLUSHING.value:
            return "flushing_work_key"
        if status_value == ExecutionStatus.FAILED.value:
            return "retryable_failed_work_key"

        return "active_work_key"
    
    @staticmethod
    async def _append_coalesced_trigger(
        session,
        *,
        run_id: uuid.UUID,
        existing_triggers,
        coalesced_trigger: Mapping[str, Any] | None,
        now: datetime,
        reason: str | None = None,
        sample_limit: int = 50,
    ) -> None:
        if coalesced_trigger is None:
            return

        trigger_ref = dict(coalesced_trigger)
        trigger_ref["reason"] = reason or trigger_ref.get("reason") or "active_work_key"
        trigger_ref["coalesced_at"] = now.isoformat().replace("+00:00", "Z")

        trigger_sample_json = json.dumps(
            [trigger_ref],
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )

        await session.execute(
            text(
                """
                UPDATE runs
                SET
                    coalesced_trigger_count = COALESCE(coalesced_trigger_count, 0) + 1,
                    coalesced_triggers = (
                        SELECT COALESCE(jsonb_agg(item ORDER BY ord), '[]'::jsonb)
                        FROM (
                            SELECT item, ord
                            FROM jsonb_array_elements(
                                COALESCE(coalesced_triggers, '[]'::jsonb)
                                || CAST(:trigger_sample AS jsonb)
                            ) WITH ORDINALITY AS elems(item, ord)
                            ORDER BY ord DESC
                            LIMIT :sample_limit
                        ) AS tail
                    ),
                    updated_at = :now
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "trigger_sample": trigger_sample_json,
                "sample_limit": sample_limit,
                "now": now,
            },
        )

    @staticmethod
    def _node_run_claim_from_row(row) -> NodeRunClaim:
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
        event = dict(row.get("run_payload") or row["payload"] or {})
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
