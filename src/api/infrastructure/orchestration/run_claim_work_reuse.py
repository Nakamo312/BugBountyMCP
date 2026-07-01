"""Work-key reuse and race recovery for node-run claims."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError

from api.application.contracts import ExecutionMode, NodeRunClaim, NodeRunClaimRequest
from api.infrastructure.orchestration.run_claim_models import (
    ExistingWorkClaim,
    blocked_node_run_claim,
    existing_work_claim,
    work_dedup_reason,
)

SelectNodeRunClaim = Callable[..., Awaitable[NodeRunClaim | None]]
SelectWorkClaim = Callable[..., Awaitable[ExistingWorkClaim | Mapping[str, Any] | None]]
SelectRecentCompletedWork = Callable[..., Awaitable[Mapping[str, Any] | None]]
AppendCoalescedTrigger = Callable[..., Awaitable[None]]


async def try_reuse_retryable_work(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
    select_retryable_failed_work_claim: SelectWorkClaim,
    append_coalesced_trigger: AppendCoalescedTrigger,
) -> NodeRunClaim | None:
    if not _retry_reuse_enabled(request):
        return None

    existing = await select_retryable_failed_work_claim(
        session,
        work_key=request.work_key,
        retry_policy=request.retry_policy,
    )
    existing = existing_work_claim(existing)
    if existing is None:
        return None

    await append_work_trigger(
        session,
        existing=existing,
        coalesced_trigger=request.coalesced_trigger,
        now=now,
        append_coalesced_trigger=append_coalesced_trigger,
    )
    return existing.to_node_run_claim()


async def check_cooldown_block(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
    select_recent_completed_work: SelectRecentCompletedWork,
) -> NodeRunClaim | None:
    since = cooldown_cutoff(request, now)
    if since is None:
        return None

    recent_work = await select_recent_completed_work(
        session,
        work_key=request.work_key,
        since=since,
    )
    if recent_work is None:
        return None
    return blocked_node_run_claim(request.claim_key, "cooldown_active")


async def recover_from_insert_race(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
    insert_error: IntegrityError,
    select_node_run_claim: SelectNodeRunClaim,
    select_active_work_claim: SelectWorkClaim,
    append_coalesced_trigger: AppendCoalescedTrigger,
) -> NodeRunClaim:
    await session.rollback()
    existing = await select_node_run_claim(session, request.claim_key)
    if existing is not None:
        return existing

    if request.execution_mode == ExecutionMode.SCHEDULED and request.work_key:
        existing_work = await select_active_work_claim(session, work_key=request.work_key)
        existing_work = existing_work_claim(existing_work)
        if existing_work is not None:
            await append_work_trigger(
                session,
                existing=existing_work,
                coalesced_trigger=request.coalesced_trigger,
                now=now,
                append_coalesced_trigger=append_coalesced_trigger,
            )
            await session.commit()
            return existing_work.to_node_run_claim()
    raise insert_error


async def append_work_trigger(
    session,
    *,
    existing: ExistingWorkClaim,
    coalesced_trigger: Mapping[str, Any] | None,
    now: datetime,
    append_coalesced_trigger: AppendCoalescedTrigger,
) -> None:
    await append_coalesced_trigger(
        session,
        run_id=existing.id,
        coalesced_trigger=coalesced_trigger,
        now=now,
        reason=work_dedup_reason(existing.status),
    )


def cooldown_cutoff(request: NodeRunClaimRequest, now: datetime) -> datetime | None:
    if (
        request.execution_mode != ExecutionMode.SCHEDULED
        or not request.work_key
        or request.cooldown_seconds <= 0
    ):
        return None
    return now - timedelta(seconds=float(request.cooldown_seconds))


def _retry_reuse_enabled(request: NodeRunClaimRequest) -> bool:
    return bool(
        request.execution_mode == ExecutionMode.SCHEDULED
        and request.work_key
        and request.retry_policy
    )
