"""SQLAlchemy statement builders for node-run claim persistence."""
from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, cast, func, insert, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB

from api.application.campaign_lifecycle import TERMINAL_CAMPAIGN_STATUSES
from api.application.contracts import ExecutionMode, ExecutionStatus
from api.infrastructure.adapters.orm import campaigns, jobs, runs
from api.infrastructure.orchestration.run_claim_models import CampaignBudgetReservation


def append_coalesced_trigger_statement():
    """Build the atomic coalesced-trigger append statement without raw SQL text."""

    empty_jsonb = cast(literal([]), JSONB)
    current_triggers = func.coalesce(runs.c.coalesced_triggers, empty_jsonb)
    new_trigger_sample = cast(bindparam("trigger_sample"), JSONB)
    combined_triggers = current_triggers.op("||")(new_trigger_sample)
    trigger_elements = (
        func.jsonb_array_elements(combined_triggers)
        .table_valued(
            "item",
            with_ordinality="ord",
        )
        .render_derived()
    )
    trigger_tail = (
        select(trigger_elements.c.item, trigger_elements.c.ord)
        .order_by(trigger_elements.c.ord.desc())
        .limit(bindparam("sample_limit"))
        .subquery("tail")
    )
    trimmed_triggers = (
        select(
            func.coalesce(
                func.jsonb_agg(trigger_tail.c.item.op("ORDER BY")(trigger_tail.c.ord)),
                empty_jsonb,
            )
        )
        .scalar_subquery()
    )
    return (
        update(runs)
        .where(runs.c.id == bindparam("run_id"))
        .values(
            coalesced_trigger_count=func.coalesce(runs.c.coalesced_trigger_count, 0) + 1,
            coalesced_triggers=trimmed_triggers,
            updated_at=bindparam("now"),
        )
    )


def node_run_claim_select(claim_key: str):
    return select(
        runs.c.id,
        runs.c.claim_key,
        runs.c.status,
        runs.c.terminal_outcome,
    ).where(runs.c.claim_key == claim_key)


def active_work_claim_select(*, work_key: str):
    return (
        select(
            runs.c.id,
            runs.c.claim_key,
            runs.c.status,
            runs.c.terminal_outcome,
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


def recent_completed_work_select(*, work_key: str, since: datetime):
    return (
        select(runs.c.id)
        .where(runs.c.execution_mode == ExecutionMode.SCHEDULED.value)
        .where(runs.c.work_key == work_key)
        .where(runs.c.status == ExecutionStatus.COMPLETED.value)
        .where(runs.c.finished_at.is_not(None))
        .where(runs.c.finished_at >= since)
        .order_by(runs.c.finished_at.desc())
        .limit(1)
    )


def campaign_budget_lock_select(*, campaign_id: uuid.UUID):
    return (
        select(
            campaigns.c.max_runs,
            campaigns.c.max_targets,
            campaigns.c.runs_consumed,
            campaigns.c.targets_consumed,
            campaigns.c.token_capacity,
            campaigns.c.tokens_available,
            campaigns.c.token_refill_per_second,
            campaigns.c.tokens_refilled_at,
        )
        .where(campaigns.c.id == campaign_id)
        .with_for_update()
    )


def retryable_failed_work_claim_select(*, work_key: str, retry_policy: dict):
    terminal_outcomes = list(retry_policy.get("terminal_outcomes") or [])
    max_attempts = int(retry_policy.get("max_attempts", 1) or 1)
    if not terminal_outcomes or max_attempts <= 1:
        return None

    return (
        select(
            runs.c.id,
            runs.c.claim_key,
            runs.c.status,
            runs.c.terminal_outcome,
        )
        .where(runs.c.execution_mode == ExecutionMode.SCHEDULED.value)
        .where(runs.c.work_key == work_key)
        .where(runs.c.status == ExecutionStatus.FAILED.value)
        .where(runs.c.terminal_outcome.in_(terminal_outcomes))
        .where(runs.c.attempt < max_attempts)
        .order_by(runs.c.updated_at.asc())
    )


def append_coalesced_trigger_parameters(
    *,
    run_id: uuid.UUID,
    coalesced_trigger: Mapping[str, Any],
    now: datetime,
    reason: str | None,
    sample_limit: int,
) -> dict[str, Any]:
    trigger_ref = dict(coalesced_trigger)
    trigger_ref["reason"] = reason or trigger_ref.get("reason") or "active_work_key"
    trigger_ref["coalesced_at"] = now.isoformat().replace("+00:00", "Z")
    return {
        "run_id": run_id,
        "trigger_sample": json.dumps(
            [trigger_ref],
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ),
        "sample_limit": sample_limit,
        "now": now,
    }


def refill_campaign_tokens_update(
    *,
    campaign_id: uuid.UUID,
    tokens_available: float,
    now: datetime,
):
    return (
        update(campaigns)
        .where(campaigns.c.id == campaign_id)
        .values(
            tokens_available=tokens_available,
            tokens_refilled_at=now,
            updated_at=now,
        )
    )


def campaign_accounting_update(
    *,
    budget: CampaignBudgetReservation,
    now: datetime,
):
    return (
        update(campaigns)
        .where(
            campaigns.c.id == budget.campaign_id,
            campaigns.c.status.notin_(TERMINAL_CAMPAIGN_STATUSES),
        )
        .values(
            status="expanding",
            tokens_refilled_at=now,
            updated_at=now,
            **budget.snapshot.consumed_values(
                target_count=budget.target_cost,
                token_cost=budget.token_cost,
            ),
        )
    )


def job_running_update(*, job_id: uuid.UUID, now: datetime):
    return (
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(
            status=ExecutionStatus.RUNNING.value,
            updated_at=now,
        )
    )


def claimed_run_insert_values(
    *,
    run_id: uuid.UUID,
    request,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": run_id,
        "job_id": request.job_id,
        "program_id": request.program_id,
        "node_id": request.node_id,
        "event_name": request.event_name,
        "trigger_event_id": request.trigger_event_id,
        "claim_key": request.claim_key,
        "work_key": request.work_key,
        "coalesced_triggers": (
            [dict(request.coalesced_trigger)]
            if request.coalesced_trigger is not None
            else None
        ),
        "input_fingerprint": request.input_fingerprint,
        "target_fingerprint": request.target_fingerprint,
        "execution_mode": request.execution_mode.value,
        "status": ExecutionStatus.QUEUED.value,
        "attempt": 1,
        "next_run_at": request.next_run_at,
        "target_count": request.target_count,
        "run_payload": dict(request.run_payload) if request.run_payload is not None else None,
        "needs_reconcile": False,
        "created_at": now,
        "updated_at": now,
    }


def claimed_run_insert(*, run_id: uuid.UUID, request, now: datetime):
    return insert(runs).values(claimed_run_insert_values(run_id=run_id, request=request, now=now))
