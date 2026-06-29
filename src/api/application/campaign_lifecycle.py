"""Deterministic campaign lifecycle evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


TERMINAL_CAMPAIGN_STATUSES = frozenset({"closed", "cancelled", "failed"})


@dataclass(frozen=True, slots=True)
class CampaignActivityState:
    campaign_id: UUID
    program_id: UUID
    current_status: str
    runs_consumed: int
    active_runs: int
    pending_dispatches: int
    pending_projection_events: int
    pending_graph_batches: int
    projection_lag_count: int
    dead_runs: int
    last_activity_at: datetime


@dataclass(frozen=True, slots=True)
class CampaignLifecycleDecision:
    status: str
    reason: str
    quiescent: bool
    quiet_for_seconds: float


def evaluate_campaign_lifecycle(
    state: CampaignActivityState,
    *,
    now: datetime,
    quiet_window_seconds: float,
) -> CampaignLifecycleDecision:
    quiet_for = max((now - state.last_activity_at).total_seconds(), 0.0)
    if state.current_status in TERMINAL_CAMPAIGN_STATUSES:
        return CampaignLifecycleDecision(
            status=state.current_status,
            reason="terminal_status",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if state.current_status == "created":
        return CampaignLifecycleDecision(
            status="created",
            reason="campaign_not_started",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if state.active_runs:
        expanding = state.runs_consumed > 0
        return CampaignLifecycleDecision(
            status="expanding" if expanding else "running",
            reason="active_expansion" if expanding else "active_execution",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if state.dead_runs:
        return CampaignLifecycleDecision(
            status="failed",
            reason="dead_run",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if state.pending_dispatches:
        return CampaignLifecycleDecision(
            status="expanding",
            reason="pending_dispatch",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if (
        state.pending_projection_events
        or state.pending_graph_batches
        or state.projection_lag_count
    ):
        return CampaignLifecycleDecision(
            status="waiting_for_projections",
            reason="projection_backlog",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    if quiet_for < max(float(quiet_window_seconds), 0.0):
        return CampaignLifecycleDecision(
            status="waiting_for_projections",
            reason="quiet_window",
            quiescent=False,
            quiet_for_seconds=quiet_for,
        )
    return CampaignLifecycleDecision(
        status="quiescent",
        reason="campaign_quiescent",
        quiescent=True,
        quiet_for_seconds=quiet_for,
    )
