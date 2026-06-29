from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.application.campaign_lifecycle import CampaignActivityState
from api.infrastructure.orchestration.store import OrchestrationStore


def test_campaign_activity_query_covers_execution_outbox_and_projections() -> None:
    query = OrchestrationStore._campaign_activity_query(
        program_id=uuid4(),
        campaign_id=uuid4(),
    )
    sql = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "FROM runs JOIN jobs" in sql
    assert "FROM event_dispatches JOIN event_store" in sql
    assert "FROM graph_projection_events" in sql
    assert "FROM graph_fact_batches" in sql
    assert "FROM projection_watermarks" in sql
    assert "campaign_id" in sql
    assert "lag_count" in sql


def test_campaign_activity_row_maps_to_application_state() -> None:
    campaign_id = uuid4()
    program_id = uuid4()
    last_activity_at = datetime.now(timezone.utc)

    state = OrchestrationStore._campaign_activity_from_row(
        {
            "campaign_id": campaign_id,
            "program_id": program_id,
            "current_status": "expanding",
            "runs_consumed": 4,
            "active_runs": 2,
            "pending_dispatches": 1,
            "pending_projection_events": 3,
            "pending_graph_batches": 5,
            "projection_lag_count": 7,
            "dead_runs": 0,
            "last_activity_at": last_activity_at,
        }
    )

    assert state == CampaignActivityState(
        campaign_id=campaign_id,
        program_id=program_id,
        current_status="expanding",
        runs_consumed=4,
        active_runs=2,
        pending_dispatches=1,
        pending_projection_events=3,
        pending_graph_batches=5,
        projection_lag_count=7,
        dead_runs=0,
        last_activity_at=last_activity_at,
    )


class RecordingLifecycleStore(OrchestrationStore):
    def __init__(self, state: CampaignActivityState) -> None:
        super().__init__(lambda: None)
        self.state = state
        self.persisted = []

    async def get_campaign_activity(self, **kwargs):
        return self.state

    async def _persist_campaign_lifecycle(self, **kwargs):
        self.persisted.append(kwargs)
        return True


async def test_reconcile_campaign_persists_deterministic_transition() -> None:
    now = datetime.now(timezone.utc)
    state = CampaignActivityState(
        campaign_id=uuid4(),
        program_id=uuid4(),
        current_status="running",
        runs_consumed=1,
        active_runs=0,
        pending_dispatches=0,
        pending_projection_events=0,
        pending_graph_batches=0,
        projection_lag_count=0,
        dead_runs=0,
        last_activity_at=now,
    )
    store = RecordingLifecycleStore(state)

    decision = await store.reconcile_campaign_lifecycle(
        program_id=state.program_id,
        campaign_id=state.campaign_id,
        now=now,
        quiet_window_seconds=30,
    )

    assert decision is not None
    assert decision.status == "waiting_for_projections"
    assert store.persisted[0]["status"] == "waiting_for_projections"
    assert store.persisted[0]["active_runs"] == 0


def test_terminal_campaign_transition_contract_is_explicit() -> None:
    assert OrchestrationStore._validate_terminal_campaign_status("closed") == "closed"
    assert OrchestrationStore._validate_terminal_campaign_status("cancelled") == "cancelled"
    assert OrchestrationStore._validate_terminal_campaign_status("failed") == "failed"
