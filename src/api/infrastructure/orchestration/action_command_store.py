"""Scenario-owned persistence for action command creation and queuing."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    EventEnvelope,
    ResolvedActionCommand,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.services.action_errors import ActionSubmissionConflict
from api.infrastructure.adapters.orm import action_requests, scope_decisions
from api.infrastructure.orchestration.action_write_helpers import (
    action_request_payload,
    catalog_hash,
    insert_job_run_and_dispatch,
    insert_policy_decision_row,
    record_action_detail_rows,
    record_approval_request_if_needed,
)
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore
from api.infrastructure.orchestration.dispatch_store import DispatchStore


def is_duplicate_action_request_integrity_error(exc: IntegrityError) -> bool:
    """Return true only for duplicate action_requests primary-key conflicts."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    message = str(orig).lower() if orig is not None else ""
    return constraint_name == "action_requests_pkey" or (
        getattr(orig, "pgcode", None) == "23505"
        and "action_requests" in message
        and "action_requests_pkey" in message
    )


def raise_submission_conflict_for_duplicate_action(action_id: uuid.UUID, exc: IntegrityError) -> None:
    if is_duplicate_action_request_integrity_error(exc):
        raise ActionSubmissionConflict(str(action_id)) from exc


class ActionCommandStore:
    """Durable write model for action requests and queued execution commands."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        campaigns: CampaignStateStore,
        dispatches: DispatchStore,
    ):
        self.session_factory = session_factory
        self.campaigns = campaigns
        self.dispatches = dispatches

    async def record_policy_result(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> uuid.UUID:
        now = datetime.now(timezone.utc)
        status = "queued" if decision.status == PolicyDecisionStatus.ALLOWED else decision.status.value

        async with self.session_factory() as session:
            try:
                await self.campaigns.upsert_campaign(session, action, now)
                await self._insert_action_request(
                    session,
                    action=action,
                    decision=decision,
                    status=status,
                    now=now,
                )
                await insert_policy_decision_row(
                    session,
                    action=action,
                    decision=decision,
                    now=now,
                )
                scope_id = await record_action_detail_rows(
                    session,
                    action=action,
                    decision=decision,
                    now=now,
                )
                await record_approval_request_if_needed(
                    session,
                    action=action,
                    decision=decision,
                    now=now,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise_submission_conflict_for_duplicate_action(action.action_id, exc)
                raise
        return scope_id

    async def create_allowed_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: uuid.UUID,
    ) -> None:
        """Persist allowed action state and its outbox delivery atomically."""
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            try:
                await self.campaigns.upsert_campaign(session, action, now)
                await self.campaigns.activate_campaign(
                    session,
                    campaign_id=action.campaign_id,
                    status="running",
                    now=now,
                )
                await self._insert_action_request(
                    session,
                    action=action,
                    decision=decision,
                    status="queued",
                    now=now,
                )
                await insert_policy_decision_row(
                    session,
                    action=action,
                    decision=decision,
                    now=now,
                )
                await record_action_detail_rows(
                    session,
                    action=action,
                    decision=decision,
                    now=now,
                    scope_decision_id=scope_id,
                )
                await insert_job_run_and_dispatch(
                    session,
                    action=action,
                    envelope=envelope,
                    dispatches=self.dispatches,
                    now=now,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise_submission_conflict_for_duplicate_action(action.action_id, exc)
                raise
            except Exception:
                await session.rollback()
                raise

    async def create_queued_job(
        self,
        action: ResolvedActionCommand,
        envelope: EventEnvelope,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            await self.campaigns.activate_campaign(
                session,
                campaign_id=action.campaign_id,
                status="running",
                now=now,
            )
            await session.execute(
                update(action_requests)
                .where(action_requests.c.id == action.action_id)
                .values(status="queued", updated_at=now)
            )
            await insert_job_run_and_dispatch(
                session,
                action=action,
                envelope=envelope,
                dispatches=self.dispatches,
                now=now,
            )
            await session.commit()

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

    @staticmethod
    async def _insert_action_request(
        session,
        *,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        status: str,
        now: datetime,
    ) -> None:
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
                catalog_hash=catalog_hash(decision),
                metadata=action.metadata,
                status=status,
                request=action_request_payload(action),
                created_at=now,
                updated_at=now,
            )
        )
