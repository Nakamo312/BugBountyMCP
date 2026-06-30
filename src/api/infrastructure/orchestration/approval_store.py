"""Scenario-owned persistence for approval decisions and approval-time queuing."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionRequest,
    EventEnvelope,
    ResolvedActionCommand,
    PolicyDecision,
)
from api.infrastructure.adapters.orm import action_requests, approval_decisions, approval_requests
from api.infrastructure.orchestration.action_write_helpers import (
    insert_job_run_and_dispatch,
    insert_policy_decision_row,
)
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore
from api.infrastructure.orchestration.dispatch_store import DispatchStore


async def record_approval_decision(
    session,
    *,
    action: ResolvedActionCommand,
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


class ApprovalStore:
    """Durable write model for approval state transitions."""

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

    async def get_action_for_approval(
        self,
        action_id: uuid.UUID,
    ) -> tuple[ActionRequest | None, str | None]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(action_requests.c.request, action_requests.c.status).where(
                    action_requests.c.id == action_id
                )
            )
            row = result.mappings().one_or_none()

        if row is None:
            return None, None
        return ActionRequest.model_validate(row["request"]), row["status"]

    async def approve_and_create_queued_job(
        self,
        action: ResolvedActionCommand,
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
                .values(status="queued", updated_at=now)
            )
            if transition.rowcount != 1:
                await session.rollback()
                return False
            await self.campaigns.activate_campaign(
                session,
                campaign_id=action.campaign_id,
                status="running",
                now=now,
            )
            await insert_policy_decision_row(
                session,
                action=action,
                decision=decision,
                now=now,
            )
            await record_approval_decision(
                session,
                action=action,
                decision=decision,
                status="approved",
                decided_by=decision.metadata.get("approved_by", "api"),
                reason="; ".join(decision.reasons) if decision.reasons else None,
                now=now,
            )
            await insert_job_run_and_dispatch(
                session,
                action=action,
                envelope=envelope,
                dispatches=self.dispatches,
                now=now,
            )
            await session.commit()
            return True

    async def reject_action(
        self,
        action: ResolvedActionCommand,
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
                .values(status="rejected", updated_at=now)
            )
            if transition.rowcount != 1:
                await session.rollback()
                return False
            await insert_policy_decision_row(
                session,
                action=action,
                decision=decision,
                now=now,
            )
            await record_approval_decision(
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
