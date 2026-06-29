from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.infrastructure.program_projection_overview import ProgramProjectionOverviewStore


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _Session:
    def __init__(self, *, fresh=True, include_state=True, queue_rows=None):
        self.program_id = uuid4()
        self.snapshot_id = uuid4()
        self.stale_snapshot_id = uuid4()
        self.analysis_run_id = uuid4()
        self.stale_analysis_run_id = uuid4()
        self.created_at = datetime(2026, 6, 27, 3, 0, tzinfo=timezone.utc)
        self.fresh = fresh
        self.include_state = include_state
        self.queue_rows = queue_rows or {}
        self.queries: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params):
        text = str(query)
        self.queries.append((text, dict(params)))
        if "FROM surface_snapshots" in text:
            if not self.include_state:
                return _Result([])
            return _Result([
                {
                    "id": self.snapshot_id,
                    "snapshot_fingerprint": "s" * 64,
                    "algorithm": "surface-map",
                    "algorithm_version": "surface-map-v1",
                    "created_at": self.created_at,
                    "node_count": 11,
                    "edge_count": 7,
                    "delta_count": 3,
                }
            ])
        if "FROM surface_component_analysis_runs" in text:
            if not self.include_state:
                return _Result([])
            snapshot_filter = params.get("snapshot_id")
            if snapshot_filter is not None:
                if self.fresh and snapshot_filter == self.snapshot_id:
                    return _Result([self._analysis_row(self.analysis_run_id, self.snapshot_id)])
                return _Result([])
            return _Result([
                self._analysis_row(
                    self.analysis_run_id if self.fresh else self.stale_analysis_run_id,
                    self.snapshot_id if self.fresh else self.stale_snapshot_id,
                )
            ])
        if "FROM graph_projection_events" in text:
            return _Result(self.queue_rows.get("graph_projection_events", [{"status": "processed", "count": 2}]))
        if "FROM graph_fact_batches" in text:
            return _Result(self.queue_rows.get("graph_fact_batches", [{"status": "applied", "count": 9}]))
        if "FROM surface_component_analysis_events" in text:
            return _Result(self.queue_rows.get("surface_component_analysis_events", [{"status": "processed", "count": 1}]))
        if "FROM search_projection_events" in text and "GROUP BY" in text:
            return _Result(self.queue_rows.get("search_projection_events", [{"status": "processed", "count": 2}]))
        if "FROM action_experience_proposals" in text:
            return _Result([{"status": "pending", "count": 4}, {"status": "suppressed", "count": 1}])
        if "FROM search_projection_events" in text and "target" in text:
            source_id = params.get("source_id")
            if source_id in {self.analysis_run_id, self.snapshot_id}:
                return _Result([
                    {
                        "status": "processed",
                        "processed_at": self.created_at,
                        "updated_at": self.created_at,
                        "created_at": self.created_at,
                    }
                ])
            return _Result([])
        raise AssertionError(text)

    def _analysis_row(self, analysis_run_id, snapshot_id):
        return {
            "id": analysis_run_id,
            "snapshot_id": snapshot_id,
            "previous_snapshot_id": None,
            "report_fingerprint": "a" * 64,
            "algorithm": "surface-component-report",
            "algorithm_version": "surface-component-analysis-v1",
            "created_at": self.created_at,
            "item_count": 5,
        }


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_program_projection_overview_store_reports_fresh_pipeline() -> None:
    session = _Session(fresh=True)
    store = ProgramProjectionOverviewStore(_SessionFactory(session))

    overview = await store.overview(program_id=session.program_id)

    assert overview is not None
    assert overview.latest_surface_snapshot is not None
    assert overview.latest_surface_snapshot.node_count == 11
    assert overview.latest_surface_analysis is not None
    assert overview.latest_surface_analysis.item_count == 5
    assert overview.surface_analysis_fresh is True
    assert overview.search_index_fresh is True
    assert overview.ui_data_fresh is True
    assert overview.graph_projection_events.processed == 2
    assert overview.graph_fact_batches.processed == 0
    assert overview.graph_fact_batches.applied == 9
    assert overview.experience_proposals.pending == 4
    assert overview.experience_proposals.suppressed == 1
    assert overview.boundary["gds_execution"] == "forbidden"


@pytest.mark.asyncio
async def test_program_projection_overview_store_keeps_applied_batches_separate_from_processed() -> None:
    session = _Session(
        fresh=True,
        queue_rows={
            "graph_fact_batches": [
                {"status": "applied", "count": 4},
                {"status": "processed", "count": 2},
            ]
        },
    )
    store = ProgramProjectionOverviewStore(_SessionFactory(session))

    overview = await store.overview(program_id=session.program_id)

    assert overview is not None
    assert overview.graph_fact_batches.applied == 4
    assert overview.graph_fact_batches.processed == 2


@pytest.mark.asyncio
async def test_program_projection_overview_store_suggests_materialization_when_analysis_is_stale() -> None:
    session = _Session(fresh=False)
    store = ProgramProjectionOverviewStore(_SessionFactory(session))

    overview = await store.overview(program_id=session.program_id)

    assert overview is not None
    assert overview.latest_surface_analysis is not None
    assert overview.latest_surface_analysis.snapshot_id == session.stale_snapshot_id
    assert overview.surface_analysis_fresh is False
    assert overview.search_index_fresh is False
    assert overview.ui_data_fresh is False
    assert any("process-surface-analysis-events" in command for command in overview.suggested_commands)
    assert any("surface-components-materialize" in command for command in overview.suggested_commands)


@pytest.mark.asyncio
async def test_program_projection_overview_store_treats_pending_or_locked_work_as_not_fresh() -> None:
    session = _Session(
        fresh=True,
        queue_rows={
            "graph_projection_events": [{"status": "locked", "count": 1}],
            "search_projection_events": [{"status": "pending", "count": 1}],
        },
    )
    store = ProgramProjectionOverviewStore(_SessionFactory(session))

    overview = await store.overview(program_id=session.program_id)

    assert overview is not None
    assert overview.surface_analysis_fresh is True
    assert overview.search_index_fresh is True
    assert overview.ui_data_fresh is False
    assert overview.graph_projection_events.backlog_count == 1
    assert overview.search_projection_events.backlog_count == 1
    assert any("process-projection-events" in command for command in overview.suggested_commands)
    assert any("process-events" in command for command in overview.suggested_commands)


@pytest.mark.asyncio
async def test_program_projection_overview_store_returns_none_without_surface_state() -> None:
    session = _Session(include_state=False)
    store = ProgramProjectionOverviewStore(_SessionFactory(session))

    assert await store.overview(program_id=session.program_id) is None
