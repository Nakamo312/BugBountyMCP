from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_materialization import SurfaceComponentAnalysisStore
    from graph_projector.surface_component_report import SurfaceComponentReport
    from graph_projector.surface_gds import (
        SurfaceComponentActionCandidate,
        SurfaceComponentBridgeProfile,
        SurfaceComponentCoverageProfile,
        SurfaceComponentDrift,
        SurfaceComponentOutlierProfile,
        SurfaceComponentProfile,
    )

    return (
        SurfaceComponentAnalysisStore,
        SurfaceComponentReport,
        SurfaceComponentProfile,
        SurfaceComponentDrift,
        SurfaceComponentBridgeProfile,
        SurfaceComponentOutlierProfile,
        SurfaceComponentCoverageProfile,
        SurfaceComponentActionCandidate,
    )


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
        if "INSERT INTO surface_component_analysis_runs" in self.query:
            return {"id": self.connection.analysis_run_id}
        if "FROM surface_component_analysis_runs" in self.query:
            return {
                "id": self.connection.analysis_run_id,
                "program_id": "11111111-1111-1111-1111-111111111111",
                "snapshot_id": "22222222-2222-2222-2222-222222222222",
                "previous_snapshot_id": None,
                "algorithm": "surface-component-report",
                "algorithm_version": "surface-component-analysis-v1",
                "report_fingerprint": "a" * 64,
                "settings_json": {"limit": 10},
                "stats_json": {"component_count": 1},
                "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        return None

    def fetchall(self):
        if "FROM surface_component_analysis_items" in self.query:
            return [
                {
                    "component_id": 1,
                    "node_count": 5,
                    "changed_node_count": 2,
                    "structural_pressure_score": 73,
                    "drift_score": 81,
                    "bridge_pressure_score": 66,
                    "outlier_score": 72,
                    "coverage_score": 55,
                    "exploration_priority_score": 34,
                    "action_candidate_count": 1,
                    "metrics_json": {"profile": {"component_id": 1}},
                    "action_candidates_json": [{"capability_id": "katana", "profile_id": "safe-crawl"}],
                }
            ]
        return []


class FakeConnection:
    def __init__(self) -> None:
        self.analysis_run_id = uuid4()
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


def _report():
    (
        _,
        Report,
        Profile,
        Drift,
        Bridge,
        Outlier,
        Coverage,
        Candidate,
    ) = _symbols()
    return Report(
        program_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="22222222-2222-2222-2222-222222222222",
        previous_snapshot_id=None,
        profiles=(Profile(1, 5, 2, 18.0, 80, 1.8, 4.0, 0.4, 73),),
        drift=(Drift(1, 3, 5, 4, 2, 3, 2, 0.33, 22.0, 70, 81),),
        bridges=(Bridge(1, 5, 2, 1.2, 8.0, 1.8, 4.0, 0.4, 80, 66),),
        outliers=(Outlier(1, 5, 2, 0.12, 0.25, 4, 0.4, 80, 72),),
        coverage=(Coverage(1, 5, 2, 1, 1, 0, 6.0, 0.4, 80, 55, 34),),
        action_candidates=(Candidate(1, 5, 2, 80, "katana", "safe-crawl", 4, 0.44, 5.0, 0.25, 0.0, 2.5, 70, 61),),
    )


def test_surface_component_analysis_store_materializes_report_items() -> None:
    Store = _symbols()[0]
    connection = FakeConnection()

    result = Store(connection).materialize(_report(), settings_json={"limit": 10})

    assert result.analysis_run_id == connection.analysis_run_id
    assert result.item_count == 1
    assert result.action_candidate_count == 1
    assert connection.commits == 1
    assert any("INSERT INTO surface_component_analysis_runs" in query for query in connection.queries)
    assert any("INSERT INTO surface_component_analysis_items" in query for query in connection.queries)
    item_params = [params for params in connection.parameters if params.get("component_id") == 1][0]
    assert item_params["structural_pressure_score"] == 73
    assert item_params["drift_score"] == 81
    assert item_params["action_candidate_count"] == 1
    assert item_params["action_candidates_json"][0]["capability_id"] == "katana"


def test_surface_component_analysis_store_reads_latest_materialized_report() -> None:
    Store = _symbols()[0]
    report = Store(FakeConnection()).latest(
        program_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="22222222-2222-2222-2222-222222222222",
    )

    assert report is not None
    assert report.item_count == 1
    assert report.items[0].component_id == 1
    assert report.items[0].exploration_priority_score == 34
    assert report.items[0].action_candidates_json[0]["capability_id"] == "katana"
    payload = report.to_dict()
    assert payload["items"][0]["structural_pressure_score"] == 73


def test_graph_projector_cli_exposes_surface_component_materialization_commands() -> None:
    source = graph_projector_cli_source()

    assert '"surface-components-materialize"' in source
    assert '"surface-components-materialized"' in source
    assert "SurfaceComponentAnalysisStore" in source


def test_surface_component_analysis_latest_uses_static_previous_snapshot_predicate() -> None:
    Store = _symbols()[0]
    connection = FakeConnection()

    Store(connection).latest(
        program_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="22222222-2222-2222-2222-222222222222",
        previous_snapshot_id=None,
    )
    latest_query = next(query for query in connection.queries if "FROM surface_component_analysis_runs" in query)
    latest_params = next(params for query, params in zip(connection.queries, connection.parameters) if "FROM surface_component_analysis_runs" in query)

    assert "previous_snapshot_id IS NULL" in latest_query
    assert "previous_snapshot_id = %(previous_snapshot_id)s" in latest_query
    assert "{_previous_snapshot_clause" not in latest_query
    assert latest_params["previous_snapshot_id"] is None


def test_surface_component_analysis_latest_binds_previous_snapshot_id_when_requested() -> None:
    Store = _symbols()[0]
    connection = FakeConnection()
    previous_snapshot_id = "33333333-3333-3333-3333-333333333333"

    Store(connection).latest(
        program_id="11111111-1111-1111-1111-111111111111",
        snapshot_id="22222222-2222-2222-2222-222222222222",
        previous_snapshot_id=previous_snapshot_id,
    )
    latest_params = next(params for query, params in zip(connection.queries, connection.parameters) if "FROM surface_component_analysis_runs" in query)

    assert latest_params["previous_snapshot_id"] == previous_snapshot_id
