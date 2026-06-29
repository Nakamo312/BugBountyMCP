from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_analysis_events import (
        SearchProjectionEventPublisher,
        SurfaceComponentAnalysisEventStore,
        SurfaceComponentAnalysisEventWorker,
        enqueue_surface_analysis_events_from_batch,
    )
    from graph_projector.contracts import GraphFactBatch, GraphNodeFact

    return SearchProjectionEventPublisher, SurfaceComponentAnalysisEventStore, SurfaceComponentAnalysisEventWorker, enqueue_surface_analysis_events_from_batch, GraphFactBatch, GraphNodeFact


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.query = ""
        self.parameters: dict[str, object] = {}

    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object:
        self.query = query
        self.parameters = parameters or {}
        self.connection.queries.append(query)
        self.connection.parameters.append(self.parameters)
        return None

    def fetchone(self):
        if "SELECT from_snapshot_id" in self.query:
            return {"from_snapshot_id": self.connection.previous_snapshot_id}
        if "SELECT previous.id" in self.query:
            return None
        if "INSERT INTO surface_component_analysis_events" in self.query:
            return {"id": self.connection.event_id}
        if "INSERT INTO search_projection_events" in self.query:
            return {"id": self.connection.search_event_id}
        if "UPDATE surface_component_analysis_events" in self.query and "RETURNING id," in self.query:
            if self.connection.claim_empty:
                return None
            return {
                "id": self.connection.event_id,
                "program_id": self.connection.program_id,
                "snapshot_id": self.connection.snapshot_id,
                "previous_snapshot_id": self.connection.previous_snapshot_id,
                "event_type": "surface_map_projected",
                "analysis_version": "surface-component-analysis-v1",
                "settings_json": {"limit": 2, "include_action_candidates": False},
                "attempts": 1,
            }
        return None

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self) -> None:
        self.event_id = uuid4()
        self.search_event_id = uuid4()
        self.program_id = uuid4()
        self.snapshot_id = uuid4()
        self.previous_snapshot_id = uuid4()
        self.claim_empty = False
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeReport:
    def __init__(self, program_id: str, snapshot_id: str, previous_snapshot_id: str | None) -> None:
        self.program_id = program_id
        self.snapshot_id = snapshot_id
        self.previous_snapshot_id = previous_snapshot_id

    def to_dict(self):
        return {"program_id": self.program_id, "snapshot_id": self.snapshot_id, "previous_snapshot_id": self.previous_snapshot_id, "profiles": [], "drift": [], "bridges": [], "outliers": [], "coverage": [], "action_candidates": []}

    profiles = ()
    drift = ()
    bridges = ()
    outliers = ()
    coverage = ()
    action_candidates = ()


class FakeReportReader:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def read(self, **kwargs):
        self.calls.append(kwargs)
        return FakeReport(str(kwargs["program_id"]), str(kwargs["snapshot_id"]), kwargs.get("previous_snapshot_id"))


class FakeAnalysisStore:
    def __init__(self) -> None:
        self.materialized = 0

    def materialize(self, report, *, settings_json=None, algorithm_version="surface-component-analysis-v1"):
        self.materialized += 1
        from graph_projector.surface_component_materialization import SurfaceComponentMaterializationResult

        return SurfaceComponentMaterializationResult(
            analysis_run_id=uuid4(),
            program_id=report.program_id,
            snapshot_id=report.snapshot_id,
            previous_snapshot_id=report.previous_snapshot_id,
            report_fingerprint="a" * 64,
            item_count=0,
            action_candidate_count=0,
        )


def test_surface_component_analysis_event_store_enqueues_idempotent_surface_map_event() -> None:
    Store = _symbols()[1]
    connection = FakeConnection()

    event_id = Store(connection).enqueue_surface_map_projected(
        program_id=connection.program_id,
        snapshot_id=connection.snapshot_id,
        settings_json={"limit": 5},
    )

    assert event_id == connection.event_id
    assert any("INSERT INTO surface_component_analysis_events" in query for query in connection.queries)
    insert_params = [params for params in connection.parameters if params.get("dedupe_key")][0]
    assert insert_params["previous_snapshot_id"] == str(connection.previous_snapshot_id)
    assert "surface-component-analysis" in insert_params["dedupe_key"]


def test_surface_component_analysis_worker_processes_claimed_event() -> None:
    _, Store, Worker, *_ = _symbols()
    connection = FakeConnection()
    reader = FakeReportReader()
    analysis_store = FakeAnalysisStore()

    result = Worker(
        event_store=Store(connection),
        analysis_store=analysis_store,
        report_reader=reader,
        worker_id="worker-1",
        lock_seconds=30,
        max_attempts=3,
    ).process_one()

    assert result.status == "processed"
    assert analysis_store.materialized == 1
    assert reader.calls[0]["snapshot_id"] == str(connection.snapshot_id)
    assert reader.calls[0]["include_action_candidates"] is False
    assert any("SET status = 'processed'" in query for query in connection.queries)




def test_surface_analysis_worker_enqueues_search_projection_events_after_materialization() -> None:
    Publisher, Store, Worker, *_ = _symbols()
    connection = FakeConnection()
    reader = FakeReportReader()
    analysis_store = FakeAnalysisStore()

    result = Worker(
        event_store=Store(connection),
        analysis_store=analysis_store,
        report_reader=reader,
        worker_id="worker-1",
        lock_seconds=30,
        max_attempts=3,
        search_event_publisher=Publisher(connection),
    ).process_one()

    assert result.status == "processed"
    assert sum("INSERT INTO search_projection_events" in query for query in connection.queries) == 2
    search_params = [params for params in connection.parameters if params.get("target") in {"surface-components", "surface-deltas"}]
    assert {params["target"] for params in search_params} == {"surface-components", "surface-deltas"}
    assert any(params["filters_json"].get("analysis_run_id") for params in search_params)
    assert any(params["filters_json"].get("snapshot_id") for params in search_params)


def test_surface_map_batch_after_apply_enqueues_analysis_event() -> None:
    _, Store, _, enqueue_from_batch, GraphFactBatch, GraphNodeFact = _symbols()
    connection = FakeConnection()
    program_id = connection.program_id
    snapshot_id = connection.snapshot_id
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="surface-map",
        parser_version="surface-map.v1",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                producer="surface-map",
                confidence=1.0,
                kind="SurfaceSnapshot",
                key=str(snapshot_id),
            )
        ],
    )

    count = enqueue_from_batch(Store(connection), batch=batch, settings_json={"limit": 10})

    assert count == 1
    assert any("INSERT INTO surface_component_analysis_events" in query for query in connection.queries)


def test_graph_projector_cli_exposes_surface_analysis_event_processing() -> None:
    source = graph_projector_cli_source()

    assert '"process-surface-analysis-events"' in source
    assert '"process-surface-analysis-events-loop"' in source
    assert "SurfaceComponentAnalysisEventWorker" in source


def test_surface_analysis_event_enqueue_statement_is_static_and_bounded() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_analysis_events import _surface_analysis_event_insert_statement

    keep_existing = _surface_analysis_event_insert_statement(reset_existing=False)
    reset_existing = _surface_analysis_event_insert_statement(reset_existing=True)

    assert "{conflict_update}" not in keep_existing
    assert "{conflict_update}" not in reset_existing
    assert "ON CONFLICT (dedupe_key) DO UPDATE" in keep_existing
    assert "SET updated_at = surface_component_analysis_events.updated_at" in keep_existing
    assert "SET previous_snapshot_id = EXCLUDED.previous_snapshot_id" in reset_existing
    assert "status = 'pending'" in reset_existing


def test_search_projection_event_publisher_enqueue_statement_is_static_and_bounded() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_analysis_events import _search_projection_event_insert_statement

    keep_existing = _search_projection_event_insert_statement(reset_existing=False)
    reset_existing = _search_projection_event_insert_statement(reset_existing=True)

    assert "{conflict_update}" not in keep_existing
    assert "{conflict_update}" not in reset_existing
    assert "ON CONFLICT (dedupe_key) DO UPDATE" in keep_existing
    assert "SET updated_at = search_projection_events.updated_at" in keep_existing
    assert "SET filters_json = EXCLUDED.filters_json" in reset_existing
    assert "result_json = '{}'::jsonb" in reset_existing


def test_surface_analysis_event_state_transitions_use_worker_lease_guard() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_analysis_event_statements import (
        SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL,
        SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL,
    )

    assert "AND status = 'locked'" in SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL
    assert "AND locked_by = %(worker_id)s" in SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL
    assert "AND status = 'locked'" in SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL
    assert "AND locked_by = %(worker_id)s" in SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL
