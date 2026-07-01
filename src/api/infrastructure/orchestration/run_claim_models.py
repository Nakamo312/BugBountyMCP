"""Typed values for node-run claim workflows."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from api.application.contracts import (
    ExecutionStatus,
    NodeRunClaim,
    TerminalOutcome,
)


def refilled_tokens(
    *,
    tokens_available: float,
    token_capacity: float,
    token_refill_per_second: float,
    tokens_refilled_at: datetime,
    now: datetime,
) -> float:
    elapsed = max((now - tokens_refilled_at).total_seconds(), 0.0)
    return min(
        float(token_capacity),
        float(tokens_available) + elapsed * float(token_refill_per_second),
    )


@dataclass(frozen=True)
class ExistingWorkClaim:
    """Typed view over an already-existing run that can satisfy a claim."""

    id: uuid.UUID
    claim_key: str
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ExistingWorkClaim:
        terminal_outcome = (
            TerminalOutcome(row["terminal_outcome"])
            if row["terminal_outcome"] is not None
            else None
        )
        return cls(
            id=row["id"],
            claim_key=row["claim_key"],
            status=ExecutionStatus(row["status"]),
            terminal_outcome=terminal_outcome,
        )

    def to_node_run_claim(self) -> NodeRunClaim:
        return NodeRunClaim(
            run_id=self.id,
            claim_key=self.claim_key,
            status=self.status,
            terminal_outcome=self.terminal_outcome,
        )


@dataclass(frozen=True)
class CampaignBudgetSnapshot:
    """Typed campaign budget state locked inside a claim transaction."""

    max_runs: int
    max_targets: int
    runs_consumed: int
    targets_consumed: int
    token_capacity: float
    tokens_available: float
    token_refill_per_second: float
    tokens_refilled_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CampaignBudgetSnapshot:
        return cls(
            max_runs=int(row["max_runs"]),
            max_targets=int(row["max_targets"]),
            runs_consumed=int(row["runs_consumed"]),
            targets_consumed=int(row["targets_consumed"]),
            token_capacity=float(row["token_capacity"]),
            tokens_available=float(row["tokens_available"]),
            token_refill_per_second=float(row["token_refill_per_second"]),
            tokens_refilled_at=row["tokens_refilled_at"],
        )

    def refilled(self, now: datetime) -> CampaignBudgetSnapshot:
        return CampaignBudgetSnapshot(
            max_runs=self.max_runs,
            max_targets=self.max_targets,
            runs_consumed=self.runs_consumed,
            targets_consumed=self.targets_consumed,
            token_capacity=self.token_capacity,
            tokens_available=refilled_tokens(
                tokens_available=self.tokens_available,
                token_capacity=self.token_capacity,
                token_refill_per_second=self.token_refill_per_second,
                tokens_refilled_at=self.tokens_refilled_at,
                now=now,
            ),
            token_refill_per_second=self.token_refill_per_second,
            tokens_refilled_at=now,
        )

    def block_reason(self, *, target_count: int, token_cost: float) -> str | None:
        if self.runs_consumed + 1 > self.max_runs:
            return "campaign_run_budget_exhausted"
        if self.targets_consumed + target_count > self.max_targets:
            return "campaign_target_budget_exhausted"
        if self.tokens_available < float(token_cost):
            return "campaign_tokens_exhausted"
        return None

    def consumed_values(self, *, target_count: int, token_cost: float) -> dict[str, Any]:
        return {
            "runs_consumed": self.runs_consumed + 1,
            "targets_consumed": self.targets_consumed + target_count,
            "tokens_available": self.tokens_available - float(token_cost),
        }


@dataclass(frozen=True)
class CampaignBudgetReservation:
    """Approved budget reservation to consume with the new run insert."""

    campaign_id: uuid.UUID
    snapshot: CampaignBudgetSnapshot
    target_cost: int
    token_cost: float


def existing_work_claim(
    value: ExistingWorkClaim | Mapping[str, Any] | None,
) -> ExistingWorkClaim | None:
    if value is None or isinstance(value, ExistingWorkClaim):
        return value
    return ExistingWorkClaim.from_row(value)


def campaign_budget_snapshot(
    value: CampaignBudgetSnapshot | Mapping[str, Any],
) -> CampaignBudgetSnapshot:
    if isinstance(value, CampaignBudgetSnapshot):
        return value
    return CampaignBudgetSnapshot.from_row(value)


def blocked_node_run_claim(claim_key: str, reason: str) -> NodeRunClaim:
    return NodeRunClaim(
        run_id=None,
        claim_key=claim_key,
        status=ExecutionStatus.CANCELLED,
        terminal_outcome=TerminalOutcome.SKIPPED,
        created=False,
        blocked_reason=reason,
    )


def work_dedup_reason(status: str | ExecutionStatus | None) -> str:
    status_value = status.value if isinstance(status, ExecutionStatus) else status

    if status_value == ExecutionStatus.QUEUED.value:
        return "queued_work_key"
    if status_value == ExecutionStatus.LEASED.value:
        return "leased_work_key"
    if status_value == ExecutionStatus.RUNNING.value:
        return "running_work_key"
    if status_value == ExecutionStatus.FLUSHING.value:
        return "flushing_work_key"
    if status_value == ExecutionStatus.FAILED.value:
        return "retryable_failed_work_key"

    return "active_work_key"
