"""Shared write helpers for action command and approval stores."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import insert

from api.application.contracts import (
    ActionRequest,
    EventEnvelope,
    ExecutionStatus,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.infrastructure.adapters.orm import (
    action_request_options,
    action_request_targets,
    approval_requests,
    jobs,
    policy_decisions,
    runs,
    scope_decisions,
)
from api.infrastructure.orchestration.dispatch_store import DispatchStore
from api.infrastructure.orchestration.event_store import insert_event_store_row


def scope_status(decision: PolicyDecision) -> str:
    if decision.status == PolicyDecisionStatus.BLOCKED:
        return "blocked"
    if decision.allowed_targets and decision.blocked_targets:
        return "partial"
    if decision.allowed_targets:
        return "allowed"
    return "not_evaluated"


def target_status(target: str, decision: PolicyDecision) -> str:
    if target in decision.allowed_targets:
        return "allowed"
    if target in decision.blocked_targets:
        return "blocked"
    return "requested"


def catalog_hash(decision: PolicyDecision) -> str | None:
    value = decision.metadata.get("catalog_hash")
    return str(value) if value else None


def run_payload_for_action(action: ActionRequest) -> dict[str, Any]:
    return {
        "options": dict(action.profile.options),
        "execution_budget": action.effective_budget.model_dump(mode="json"),
    }


async def record_approval_request_if_needed(
    session,
    *,
    action: ActionRequest,
    decision: PolicyDecision,
    now: datetime,
) -> None:
    """Create a pending approval request in the caller's transaction when policy needs it."""
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


async def insert_policy_decision_row(
    session,
    *,
    action: ActionRequest,
    decision: PolicyDecision,
    now: datetime,
) -> None:
    await session.execute(
        insert(policy_decisions).values(
            id=decision.decision_id,
            action_id=action.action_id,
            status=decision.status.value,
            reasons=decision.reasons,
            allowed_targets=decision.allowed_targets,
            blocked_targets=decision.blocked_targets,
            safety_level=(
                decision.safety_level.value if decision.safety_level is not None else None
            ),
            metadata=decision.metadata,
            catalog_hash=catalog_hash(decision),
            created_at=now,
        )
    )


async def record_action_detail_rows(
    session,
    *,
    action: ActionRequest,
    decision: PolicyDecision,
    now: datetime,
    scope_decision_id: uuid.UUID | None = None,
) -> uuid.UUID:
    for position, target in enumerate(action.profile.targets):
        await session.execute(
            insert(action_request_targets).values(
                id=uuid.uuid4(),
                action_id=action.action_id,
                target=target,
                position=position,
                status=target_status(target, decision),
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
    scope_decision_id = scope_decision_id or uuid.uuid4()
    await session.execute(
        insert(scope_decisions).values(
            id=scope_decision_id,
            action_id=action.action_id,
            status=scope_status(decision),
            scope_policy=decision.metadata.get("scope_policy"),
            reasons=decision.reasons,
            allowed_targets=decision.allowed_targets,
            blocked_targets=decision.blocked_targets,
            metadata=decision.metadata,
            created_at=now,
        )
    )
    return scope_decision_id


async def insert_job_run_and_dispatch(
    session,
    *,
    action: ActionRequest,
    envelope: EventEnvelope,
    dispatches: DispatchStore,
    now: datetime,
) -> None:
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
    await dispatches.enqueue_dispatch(session, envelope, now=now)
