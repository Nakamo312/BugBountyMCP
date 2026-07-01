"""Transaction functions for action command writes."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import insert

from api.application.contracts import EventEnvelope, PolicyDecision, PolicyDecisionStatus, ResolvedActionCommand
from api.infrastructure.adapters.orm import action_requests
from api.infrastructure.orchestration.action_execution_writer import insert_queued_execution
from api.infrastructure.orchestration.action_write_helpers import (
    action_request_payload,
    catalog_hash,
    insert_policy_decision_row,
    record_action_detail_rows,
    record_approval_request_if_needed,
)
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore
from api.infrastructure.orchestration.dispatch_writer import DispatchWriterStore


async def insert_action_request(
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


async def record_policy_result_in_session(
    session,
    *,
    campaigns: CampaignWriteStore,
    action: ResolvedActionCommand,
    decision: PolicyDecision,
    now: datetime,
) -> uuid.UUID:
    status = "queued" if decision.status == PolicyDecisionStatus.ALLOWED else decision.status.value
    await campaigns.upsert_campaign(session, action, now)
    await insert_action_request(
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
    return scope_id


async def create_allowed_action_in_session(
    session,
    *,
    campaigns: CampaignWriteStore,
    dispatches: DispatchWriterStore,
    action: ResolvedActionCommand,
    decision: PolicyDecision,
    envelope: EventEnvelope,
    scope_id: uuid.UUID,
    now: datetime,
) -> None:
    await campaigns.upsert_campaign(session, action, now)
    await campaigns.activate_campaign(
        session,
        campaign_id=action.campaign_id,
        status="running",
        now=now,
    )
    await insert_action_request(
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
    await insert_queued_execution(
        session,
        action=action,
        envelope=envelope,
        now=now,
    )
    await dispatches.enqueue_dispatch(session, envelope, now=now)
