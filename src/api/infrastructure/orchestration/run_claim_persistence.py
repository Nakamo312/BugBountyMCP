"""Persistence helpers for node-run claim workflows."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from api.infrastructure.orchestration.run_claim_models import (
    CampaignBudgetReservation,
    CampaignBudgetSnapshot,
    ExistingWorkClaim,
)
from api.infrastructure.orchestration.run_claim_statements import (
    active_work_claim_select,
    append_coalesced_trigger_parameters,
    append_coalesced_trigger_statement,
    campaign_accounting_update,
    campaign_budget_lock_select,
    claimed_run_insert,
    job_running_update,
    node_run_claim_select,
    recent_completed_work_select,
    refill_campaign_tokens_update,
    retryable_failed_work_claim_select,
)


async def select_node_run_claim(session, claim_key: str):
    result = await session.execute(node_run_claim_select(claim_key))
    row = result.mappings().one_or_none()
    return ExistingWorkClaim.from_row(row).to_node_run_claim() if row is not None else None


async def select_active_work_claim(session, *, work_key: str) -> ExistingWorkClaim | None:
    result = await session.execute(active_work_claim_select(work_key=work_key))
    row = result.mappings().one_or_none()
    return ExistingWorkClaim.from_row(row) if row is not None else None


async def select_recent_completed_work(session, *, work_key: str, since: datetime):
    result = await session.execute(recent_completed_work_select(work_key=work_key, since=since))
    return result.mappings().one_or_none()


async def lock_campaign_budget(
    session,
    *,
    campaign_id: uuid.UUID,
) -> CampaignBudgetSnapshot | None:
    result = await session.execute(campaign_budget_lock_select(campaign_id=campaign_id))
    row = result.mappings().one_or_none()
    return CampaignBudgetSnapshot.from_row(row) if row is not None else None


async def select_retryable_failed_work_claim(
    session,
    *,
    work_key: str,
    retry_policy: dict,
) -> ExistingWorkClaim | None:
    statement = retryable_failed_work_claim_select(work_key=work_key, retry_policy=retry_policy)
    if statement is None:
        return None
    result = await session.execute(statement)
    row = result.mappings().one_or_none()
    return ExistingWorkClaim.from_row(row) if row is not None else None


async def append_coalesced_trigger(
    session,
    *,
    run_id: uuid.UUID,
    coalesced_trigger: Mapping[str, Any] | None,
    now: datetime,
    reason: str | None = None,
    sample_limit: int = 50,
) -> None:
    if coalesced_trigger is None:
        return
    await session.execute(
        append_coalesced_trigger_statement(),
        append_coalesced_trigger_parameters(
            run_id=run_id,
            coalesced_trigger=coalesced_trigger,
            now=now,
            reason=reason,
            sample_limit=sample_limit,
        ),
    )


async def persist_refilled_campaign_tokens(
    session,
    *,
    campaign_id: uuid.UUID,
    tokens_available: float,
    now: datetime,
) -> None:
    await session.execute(
        refill_campaign_tokens_update(
            campaign_id=campaign_id,
            tokens_available=tokens_available,
            now=now,
        )
    )


async def apply_campaign_accounting(
    session,
    *,
    job_id: uuid.UUID,
    budget: CampaignBudgetReservation,
    now: datetime,
) -> None:
    await session.execute(campaign_accounting_update(budget=budget, now=now))
    await session.execute(job_running_update(job_id=job_id, now=now))


async def insert_claimed_run(
    session,
    *,
    request,
    budget: CampaignBudgetReservation | None,
    now: datetime,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    await session.execute(claimed_run_insert(run_id=run_id, request=request, now=now))
    if budget is not None:
        await apply_campaign_accounting(
            session,
            job_id=request.job_id,
            budget=budget,
            now=now,
        )
    return run_id
