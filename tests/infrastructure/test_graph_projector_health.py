from __future__ import annotations

import sys
from pathlib import Path
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.health import GraphProjectorHealthChecker, GraphProjectorHealthThresholds
    from graph_projector.status import GraphProjectorStatusReader

    return GraphProjectorHealthChecker, GraphProjectorHealthThresholds, GraphProjectorStatusReader


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

    def fetchall(self) -> list[dict[str, object]]:
        if "FROM graph_projection_events" in self.query:
            return list(self.connection.projection_rows)
        if "FROM graph_fact_batches" in self.query:
            return list(self.connection.batch_rows)
        if "FROM surface_component_analysis_events" in self.query:
            return list(self.connection.surface_analysis_rows)
        raise AssertionError(f"unexpected query: {self.query}")


class FakeConnection:
    def __init__(
        self,
        *,
        projection_rows: list[dict[str, object]] | None = None,
        batch_rows: list[dict[str, object]] | None = None,
        surface_analysis_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.projection_rows = projection_rows or []
        self.batch_rows = batch_rows or []
        self.surface_analysis_rows = surface_analysis_rows or []
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_graph_projector_health_is_ok_when_backlogs_are_within_thresholds() -> None:
    GraphProjectorHealthChecker, GraphProjectorHealthThresholds, GraphProjectorStatusReader = _symbols()
    connection = FakeConnection(
        projection_rows=[{"source_type": "raw_artifact", "event_type": "created", "status": "pending", "count": 2}],
        batch_rows=[{"parser_version": "raw-artifact-graph-v1", "status": "pending", "count": 1}],
    )

    check = GraphProjectorHealthChecker(GraphProjectorStatusReader(connection)).check(
        thresholds=GraphProjectorHealthThresholds(
            max_pending_projection_events=2,
            max_pending_graph_fact_batches=1,
        )
    )

    assert check.ok is True
    assert check.status == "ok"
    assert check.reasons == ()
    assert check.metrics["projection_events_pending"] == 2
    assert check.metrics["graph_fact_batches_pending"] == 1


def test_graph_projector_health_reports_threshold_violations() -> None:
    GraphProjectorHealthChecker, GraphProjectorHealthThresholds, GraphProjectorStatusReader = _symbols()
    connection = FakeConnection(
        projection_rows=[
            {"source_type": "raw_artifact", "event_type": "created", "status": "failed", "count": 1},
            {"source_type": "action_outcome", "event_type": "updated", "status": "dead", "count": 2},
        ],
        batch_rows=[{"parser_version": "surface-map-graph-v1", "status": "pending", "count": 4}],
        surface_analysis_rows=[{"event_type": "surface_map_projected", "status": "failed", "count": 2}],
    )

    check = GraphProjectorHealthChecker(GraphProjectorStatusReader(connection)).check(
        thresholds=GraphProjectorHealthThresholds(
            max_pending_graph_fact_batches=3,
            max_failed_projection_events=0,
            max_dead_projection_events=0,
        )
    )

    assert check.ok is False
    assert check.status == "unhealthy"
    assert check.metrics["projection_events_failed"] == 1
    assert check.metrics["projection_events_dead"] == 2
    assert check.metrics["graph_fact_batches_pending"] == 4
    assert any("projection events failed" in reason for reason in check.reasons)
    assert any("projection events dead" in reason for reason in check.reasons)
    assert any("graph fact batches pending" in reason for reason in check.reasons)
    assert check.metrics["surface_analysis_events_failed"] == 2
    assert any("surface analysis events failed" in reason for reason in check.reasons)


def test_graph_projector_health_rejects_negative_thresholds() -> None:
    _, GraphProjectorHealthThresholds, _ = _symbols()

    try:
        GraphProjectorHealthThresholds(max_pending_projection_events=-1)
    except ValueError as exc:
        assert "max_pending_projection_events must be non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected negative threshold to fail")


def test_graph_projector_health_can_be_serialized_for_machine_readable_output() -> None:
    GraphProjectorHealthChecker, GraphProjectorHealthThresholds, GraphProjectorStatusReader = _symbols()
    connection = FakeConnection(
        projection_rows=[{"source_type": "raw_artifact", "event_type": "created", "status": "failed", "count": 1}],
        batch_rows=[],
    )

    payload = GraphProjectorHealthChecker(GraphProjectorStatusReader(connection)).check(
        thresholds=GraphProjectorHealthThresholds()
    ).to_dict()

    assert payload["ok"] is False
    assert payload["status"] == "unhealthy"
    assert payload["metrics"]["projection_events_failed"] == 1
    assert payload["thresholds"]["max_failed_projection_events"] == 0
    assert payload["thresholds"]["max_failed_surface_analysis_events"] == 0
    assert payload["reasons"]


def test_graph_projector_cli_exposes_health_command() -> None:
    source = graph_projector_cli_source()

    assert 'subparsers.add_parser("health"' in source
    assert "GraphProjectorHealthChecker" in source
    assert "GraphProjectorHealthThresholds" in source
    assert "--json" in source
    assert "return 0 if check.ok else 1" in source
