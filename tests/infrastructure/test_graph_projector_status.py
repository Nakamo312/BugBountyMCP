from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.status import GraphProjectorStatusReader

    return GraphProjectorStatusReader


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
            return [
                {
                    "source_type": "action_outcome",
                    "event_type": "action_outcome_updated",
                    "status": "pending",
                    "count": 3,
                },
                {
                    "source_type": "raw_artifact",
                    "event_type": "raw_artifact_created",
                    "status": "failed",
                    "count": 1,
                },
            ]
        if "FROM graph_fact_batches" in self.query:
            return [
                {"parser_version": "action-outcome-graph-v1", "status": "pending", "count": 2},
                {"parser_version": "surface-map-graph-v1", "status": "dead", "count": 1},
            ]
        if "FROM surface_component_analysis_events" in self.query:
            return [
                {"event_type": "surface_map_projected", "status": "pending", "count": 4},
                {"event_type": "surface_map_projected", "status": "failed", "count": 1},
            ]
        raise AssertionError(f"unexpected query: {self.query}")


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_graph_projector_status_reader_reports_durable_backlog_counts() -> None:
    GraphProjectorStatusReader = _symbols()

    report = GraphProjectorStatusReader(FakeConnection()).read()

    assert report.pending_projection_events == 3
    assert report.failed_projection_events == 1
    assert report.dead_projection_events == 0
    assert report.pending_graph_fact_batches == 2
    assert report.failed_graph_fact_batches == 0
    assert report.dead_graph_fact_batches == 1
    assert report.pending_surface_analysis_events == 4
    assert report.failed_surface_analysis_events == 1
    assert "action_outcomes" in report.rebuild_sources
    assert "surface_map" in report.rebuild_sources


def test_graph_projector_status_reader_uses_static_program_filter_contract() -> None:
    GraphProjectorStatusReader = _symbols()
    connection = FakeConnection()
    program_id = uuid4()

    GraphProjectorStatusReader(connection).read(program_id=program_id)

    assert all("%(program_id)s IS NULL OR program_id = %(program_id)s" in query for query in connection.queries)
    assert connection.parameters == [{"program_id": program_id}, {"program_id": program_id}, {"program_id": program_id}]


def test_graph_projector_status_reader_keeps_static_filter_when_program_is_not_set() -> None:
    GraphProjectorStatusReader = _symbols()
    connection = FakeConnection()

    GraphProjectorStatusReader(connection).read()

    assert all("%(program_id)s IS NULL OR program_id = %(program_id)s" in query for query in connection.queries)
    assert connection.parameters == [{"program_id": None}, {"program_id": None}, {"program_id": None}]


def test_graph_projector_cli_exposes_status_command() -> None:
    source = graph_projector_cli_source()

    assert 'subparsers.add_parser("status"' in source
    assert "GraphProjectorStatusReader" in source
    assert "projection_events_pending" in source
    assert "graph_fact_batches_pending" in source
    assert "surface_analysis_events_pending" in source
