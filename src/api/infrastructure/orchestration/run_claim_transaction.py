"""Single-session transaction flow for node-run claims."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError

from api.application.contracts import ExecutionMode, ExecutionStatus, NodeRunClaim, NodeRunClaimRequest
from api.infrastructure.orchestration.run_claim_budget import reserve_campaign_budget_if_needed
from api.infrastructure.orchestration.run_claim_models import (
    CampaignBudgetReservation,
    blocked_node_run_claim,
)
from api.infrastructure.orchestration.run_claim_persistence import (
    append_coalesced_trigger,
    insert_claimed_run,
    lock_campaign_budget,
    persist_refilled_campaign_tokens,
    select_active_work_claim,
    select_node_run_claim,
    select_recent_completed_work,
    select_retryable_failed_work_claim,
)
from api.infrastructure.orchestration.run_claim_work_reuse import (
    check_cooldown_block,
    recover_from_insert_race,
    try_reuse_retryable_work,
)


async def claim_node_run_in_session(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
) -> NodeRunClaim:
    """Claim or reuse a node run inside an already-open session."""

    existing = await select_node_run_claim(session, request.claim_key)
    if existing is not None:
        return existing

    if depth_limit_exceeded(request):
        return blocked_node_run_claim(request.claim_key, "depth_limit")

    reusable = await try_reuse_retryable_work(
        session,
        request=request,
        now=now,
        select_retryable_failed_work_claim=select_retryable_failed_work_claim,
        append_coalesced_trigger=append_coalesced_trigger,
    )
    if reusable is not None:
        await session.commit()
        return reusable

    cooldown_block = await check_cooldown_block(
        session,
        request=request,
        now=now,
        select_recent_completed_work=select_recent_completed_work,
    )
    if cooldown_block is not None:
        return cooldown_block

    budget = await reserve_budget_or_block(session, request=request, now=now)
    if isinstance(budget, NodeRunClaim):
        return budget

    try:
        run_id = await insert_claimed_run(
            session,
            request=request,
            budget=budget,
            now=now,
        )
        await session.commit()
        return NodeRunClaim(
            run_id=run_id,
            claim_key=request.claim_key,
            status=ExecutionStatus.QUEUED,
            created=True,
        )
    except IntegrityError as exc:
        return await recover_from_insert_race(
            session,
            request=request,
            now=now,
            insert_error=exc,
            select_node_run_claim=select_node_run_claim,
            select_active_work_claim=select_active_work_claim,
            append_coalesced_trigger=append_coalesced_trigger,
        )


def depth_limit_exceeded(request: NodeRunClaimRequest) -> bool:
    return (
        request.max_expansion_depth is not None
        and request.expansion_depth > request.max_expansion_depth
    )


async def reserve_budget_or_block(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
) -> CampaignBudgetReservation | NodeRunClaim | None:
    if request.execution_mode != ExecutionMode.SCHEDULED:
        return None

    budget = await reserve_campaign_budget_if_needed(
        session,
        request=request,
        now=now,
        lock_campaign_budget=lock_campaign_budget,
        persist_refilled_campaign_tokens=persist_refilled_campaign_tokens,
    )
    if isinstance(budget, NodeRunClaim):
        await session.commit()
    return budget
