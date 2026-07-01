"""Campaign budget decisions for node-run claims."""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from api.application.contracts import ExecutionMode, NodeRunClaim, NodeRunClaimRequest
from api.infrastructure.orchestration.run_claim_models import (
    CampaignBudgetReservation,
    CampaignBudgetSnapshot,
    blocked_node_run_claim,
    campaign_budget_snapshot,
)

LockCampaignBudget = Callable[..., Awaitable[CampaignBudgetSnapshot | Mapping[str, Any] | None]]
PersistRefilledCampaignTokens = Callable[..., Awaitable[None]]


async def reserve_campaign_budget_if_needed(
    session,
    *,
    request: NodeRunClaimRequest,
    now: datetime,
    lock_campaign_budget: LockCampaignBudget,
    persist_refilled_campaign_tokens: PersistRefilledCampaignTokens,
) -> CampaignBudgetReservation | NodeRunClaim | None:
    """Reserve campaign budget for scheduled claims or return a block claim.

    The run insert and successful budget consumption remain atomic in
    ``insert_claimed_run``. This function owns only the budget decision and the
    failed-reservation refill update.
    """

    if request.execution_mode != ExecutionMode.SCHEDULED or request.campaign_id is None:
        return None

    locked_budget = await lock_campaign_budget(session, campaign_id=request.campaign_id)
    if locked_budget is None:
        return blocked_node_run_claim(
            request.claim_key,
            "campaign_budget_missing",
        )

    target_cost = _target_cost(request.target_count)
    token_cost_value = _token_cost(request.token_cost)
    snapshot = campaign_budget_snapshot(locked_budget).refilled(now)
    blocked_reason = snapshot.block_reason(
        target_count=target_cost,
        token_cost=token_cost_value,
    )
    if blocked_reason is not None:
        await persist_refilled_campaign_tokens(
            session,
            campaign_id=_required_campaign_id(request.campaign_id),
            tokens_available=snapshot.tokens_available,
            now=now,
        )
        return blocked_node_run_claim(request.claim_key, blocked_reason)

    return CampaignBudgetReservation(
        campaign_id=_required_campaign_id(request.campaign_id),
        snapshot=snapshot,
        target_cost=target_cost,
        token_cost=token_cost_value,
    )


def _target_cost(target_count: int | None) -> int:
    return max(int(target_count or 0), 0)


def _token_cost(token_cost: int | float) -> float:
    return float(token_cost)


def _required_campaign_id(campaign_id: uuid.UUID | None) -> uuid.UUID:
    if campaign_id is None:
        raise ValueError("campaign_id is required after scheduled budget guard")
    return campaign_id
