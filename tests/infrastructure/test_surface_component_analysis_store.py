from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.infrastructure.surface_component_analysis import SurfaceComponentAnalysisStore


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
    def __init__(self, *, program_id, snapshot_id, previous_snapshot_id=None, has_run=True):
        self.program_id = program_id
        self.snapshot_id = snapshot_id
        self.previous_snapshot_id = previous_snapshot_id
        self.has_run = has_run
        self.analysis_run_id = uuid4()
        self.queries: list[tuple[str, dict[str, object]]] = []
        self.query_types: list[str] = []
        self.created_at = datetime(2026, 6, 27, 2, 0, tzinfo=timezone.utc)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params):
        text = str(query)
        self.query_types.append(query.__class__.__name__)
        self.queries.append((text, dict(params)))
        if "FROM surface_component_analysis_runs" in text:
            if not self.has_run:
                return _Result([])
            return _Result([
                {
                    "id": self.analysis_run_id,
                    "program_id": self.program_id,
                    "snapshot_id": self.snapshot_id,
                    "previous_snapshot_id": self.previous_snapshot_id,
                    "algorithm": "surface-component-report",
                    "algorithm_version": "surface-component-analysis-v1",
                    "report_fingerprint": "f" * 64,
                    "settings_json": {"limit": 10},
                    "stats_json": {"component_count": 1},
                    "created_at": self.created_at,
                }
            ])
        if "FROM surface_component_analysis_items" in text:
            return _Result([
                {
                    "component_id": 3,
                    "node_count": 8,
                    "changed_node_count": 2,
                    "structural_pressure_score": 75,
                    "drift_score": None,
                    "bridge_pressure_score": 52,
                    "outlier_score": 61,
                    "coverage_score": 12,
                    "exploration_priority_score": 88,
                    "action_candidate_count": 2,
                    "metrics_json": {"profile": {"component_id": 3}},
                    "action_candidates_json": [{"capability_id": "httpx"}],
                }
            ])
        raise AssertionError(text)


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_surface_component_analysis_store_reads_latest_report() -> None:
    program_id = uuid4()
    snapshot_id = uuid4()
    session = _Session(program_id=program_id, snapshot_id=snapshot_id)
    store = SurfaceComponentAnalysisStore(_SessionFactory(session))

    report = await store.latest(program_id=program_id, snapshot_id=snapshot_id)

    assert report is not None
    assert report.program_id == program_id
    assert report.snapshot_id == snapshot_id
    assert report.item_count == 1
    assert report.items[0].component_id == 3
    assert report.items[0].exploration_priority_score == 88
    assert report.items[0].action_candidates[0]["capability_id"] == "httpx"
    assert "previous_snapshot_id IS NULL" in session.queries[0][0]
    assert session.query_types == ["Select", "Select"]


@pytest.mark.asyncio
async def test_surface_component_analysis_store_filters_previous_snapshot() -> None:
    program_id = uuid4()
    snapshot_id = uuid4()
    previous_snapshot_id = uuid4()
    session = _Session(program_id=program_id, snapshot_id=snapshot_id, previous_snapshot_id=previous_snapshot_id)
    store = SurfaceComponentAnalysisStore(_SessionFactory(session))

    report = await store.latest(
        program_id=program_id,
        snapshot_id=snapshot_id,
        previous_snapshot_id=previous_snapshot_id,
    )

    assert report is not None
    assert report.previous_snapshot_id == previous_snapshot_id
    assert "previous_snapshot_id = :previous_snapshot_id" in session.queries[0][0]
    assert session.query_types == ["Select", "Select"]
    assert session.queries[0][1]["previous_snapshot_id"] == previous_snapshot_id


@pytest.mark.asyncio
async def test_surface_component_analysis_store_returns_none_when_missing() -> None:
    program_id = uuid4()
    snapshot_id = uuid4()
    session = _Session(program_id=program_id, snapshot_id=snapshot_id, has_run=False)
    store = SurfaceComponentAnalysisStore(_SessionFactory(session))

    assert await store.latest(program_id=program_id, snapshot_id=snapshot_id) is None
    assert len(session.queries) == 1
    assert session.query_types == ["Select"]


@pytest.mark.asyncio
async def test_surface_component_analysis_store_reads_latest_for_program() -> None:
    program_id = uuid4()
    snapshot_id = uuid4()
    session = _Session(program_id=program_id, snapshot_id=snapshot_id)
    store = SurfaceComponentAnalysisStore(_SessionFactory(session))

    report = await store.latest_for_program(program_id=program_id)

    assert report is not None
    assert report.program_id == program_id
    assert report.snapshot_id == snapshot_id
    assert "surface_component_analysis_runs.program_id = :program_id" in session.queries[0][0]
    assert "snapshot_id = :snapshot_id" not in session.queries[0][0]
    assert session.queries[0][1] == {"program_id": program_id}
    assert session.query_types == ["Select", "Select"]
