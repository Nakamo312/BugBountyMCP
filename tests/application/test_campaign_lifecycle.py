from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api.application.campaign_lifecycle import (
    CampaignActivityState,
    evaluate_campaign_lifecycle,
)


def _state(**overrides) -> CampaignActivityState:
    values = {
        "campaign_id": uuid4(),
        "program_id": uuid4(),
        "current_status": "running",
        "runs_consumed": 0,
        "active_runs": 0,
        "pending_dispatches": 0,
        "pending_projection_events": 0,
        "pending_graph_batches": 0,
        "projection_lag_count": 0,
        "dead_runs": 0,
        "last_activity_at": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    values.update(overrides)
    return CampaignActivityState(**values)


def test_active_initial_campaign_is_running() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(active_runs=1),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "running"
    assert decision.quiescent is False
    assert decision.reason == "active_execution"


def test_created_campaign_waiting_for_start_is_not_quiescent() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(current_status="created"),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "created"
    assert decision.quiescent is False
    assert decision.reason == "campaign_not_started"


def test_active_downstream_campaign_is_expanding() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(active_runs=1, runs_consumed=2),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "expanding"
    assert decision.reason == "active_expansion"


def test_pending_outbox_prevents_quiescence() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(pending_dispatches=1),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "expanding"
    assert decision.reason == "pending_dispatch"


def test_projection_backlog_moves_campaign_to_waiting() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(pending_projection_events=1),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "waiting_for_projections"
    assert decision.reason == "projection_backlog"


def test_ready_campaign_waits_for_quiet_window() -> None:
    now = datetime.now(timezone.utc)
    decision = evaluate_campaign_lifecycle(
        _state(last_activity_at=now - timedelta(seconds=10)),
        now=now,
        quiet_window_seconds=30,
    )

    assert decision.status == "waiting_for_projections"
    assert decision.reason == "quiet_window"
    assert decision.quiet_for_seconds == 10


def test_campaign_becomes_quiescent_after_quiet_window() -> None:
    now = datetime.now(timezone.utc)
    decision = evaluate_campaign_lifecycle(
        _state(last_activity_at=now - timedelta(seconds=31)),
        now=now,
        quiet_window_seconds=30,
    )

    assert decision.status == "quiescent"
    assert decision.quiescent is True
    assert decision.reason == "campaign_quiescent"


def test_dead_run_fails_campaign_when_no_work_can_progress() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(dead_runs=1),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "failed"
    assert decision.reason == "dead_run"


def test_dead_branch_does_not_stop_other_active_work() -> None:
    decision = evaluate_campaign_lifecycle(
        _state(active_runs=1, dead_runs=1, runs_consumed=1),
        now=datetime.now(timezone.utc),
        quiet_window_seconds=30,
    )

    assert decision.status == "expanding"
    assert decision.reason == "active_expansion"


def test_terminal_campaign_is_not_reopened() -> None:
    for status in ("closed", "cancelled", "failed"):
        decision = evaluate_campaign_lifecycle(
            _state(current_status=status, active_runs=1),
            now=datetime.now(timezone.utc),
            quiet_window_seconds=30,
        )

        assert decision.status == status
        assert decision.reason == "terminal_status"
