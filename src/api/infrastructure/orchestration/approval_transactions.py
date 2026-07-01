"""Transaction functions for approval state transitions."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import insert, select, update

from api.application.contracts import ActionRequest, EventEnvelope, PolicyDecision, ResolvedActionCommand
from api.infrastructure.adapters.orm import action_requests, approval_decisions, approval_requests, scope_decisions
from api.infrastructure.orchestration.action_execution_writer import insert_queued_execution
from api.infrastructure.orchestration.action_write_helpers import insert_policy_decision_row
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore
from api.infrastructure.orchestration.dispatch_writer import DispatchWriterStore


async def select_action_for_approval(session, *, action_id: uuid.UUID) -> tuple[ActionRequest | None, str | None]:
    result = await session.execute(
        select(action_requests.c.request, action_requests.c.status).where(
            action_requests.c.id == action_id
        )
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None, None
    return ActionRequest.model_validate(row["request"]), row["status"]


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


async def approve_and_create_queued_job_in_session(
    session,
    *,
    campaigns: CampaignWriteStore,
    dispatches: DispatchWriterStore,
    action: ResolvedActionCommand,
    decision: PolicyDecision,
    envelope: EventEnvelope,
    now: datetime,
) -> bool:
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
    await campaigns.activate_campaign(
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
    await insert_queued_execution(
        session,
        action=action,
        envelope=envelope,
        now=now,
    )
    await dispatches.enqueue_dispatch(session, envelope, now=now)
    return True


async def reject_action_in_session(
    session,
    *,
    action: ResolvedActionCommand,
    decision: PolicyDecision,
    now: datetime,
) -> bool:
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
    return True

async def select_latest_scope_id(session, *, action_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.execute(
        select(scope_decisions.c.id)
        .where(scope_decisions.c.action_id == action_id)
        .order_by(scope_decisions.c.created_at.desc())
        .limit(1)
    )
    row = result.mappings().one_or_none()
    return row["id"] if row else None
