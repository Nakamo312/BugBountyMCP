from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.diagnostics import GraphProjectorDiagnosticsReader
    from graph_projector.health import GraphProjectorHealthThresholds

    return GraphProjectorDiagnosticsReader, GraphProjectorHealthThresholds


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
        if "GROUP BY source_type, event_type, status" in self.query:
            return list(self.connection.projection_status_rows)
        if "GROUP BY parser_version, status" in self.query:
            return list(self.connection.batch_status_rows)
        if "GROUP BY event_type, status" in self.query:
            return list(self.connection.surface_analysis_status_rows)
        if "SELECT id," in self.query and "FROM graph_projection_events" in self.query:
            return list(self.connection.projection_sample_rows)
        if "SELECT id," in self.query and "FROM graph_fact_batches" in self.query:
            return list(self.connection.batch_sample_rows)
        if "SELECT id," in self.query and "FROM surface_component_analysis_events" in self.query:
            return list(self.connection.surface_analysis_sample_rows)
        raise AssertionError(f"unexpected query: {self.query}")


class FakeConnection:
    def __init__(self) -> None:
        program_id = uuid4()
        self.projection_status_rows = [
            {"source_type": "action_outcome", "event_type": "action_outcome_updated", "status": "failed", "count": 1},
            {"source_type": "raw_artifact", "event_type": "raw_artifact_created", "status": "pending", "count": 2},
        ]
        self.batch_status_rows = [
            {"parser_version": "surface-map-graph-v1", "status": "dead", "count": 1},
        ]
        self.surface_analysis_status_rows = [
            {"event_type": "surface_map_projected", "status": "failed", "count": 1},
        ]
        self.projection_sample_rows = [
            {
                "id": uuid4(),
                "program_id": program_id,
                "source_type": "action_outcome",
                "source_id": uuid4(),
                "event_type": "action_outcome_updated",
                "status": "failed",
                "attempts": 3,
                "last_error": "boom",
                "updated_at": "2026-06-27T00:00:00Z",
            }
        ]
        self.batch_sample_rows = [
            {
                "id": uuid4(),
                "program_id": program_id,
                "produced_by": "surface-map",
                "parser_version": "surface-map-graph-v1",
                "status": "dead",
                "attempts": 5,
                "fact_count": 7,
                "last_error": "nope",
                "updated_at": "2026-06-27T00:01:00Z",
            }
        ]
        self.surface_analysis_sample_rows = [
            {
                "id": uuid4(),
                "program_id": program_id,
                "snapshot_id": uuid4(),
                "previous_snapshot_id": None,
                "event_type": "surface_map_projected",
                "analysis_version": "surface-component-analysis-v1",
                "status": "failed",
                "attempts": 2,
                "last_error": "gds unavailable",
                "updated_at": "2026-06-27T00:02:00Z",
            }
        ]
        self.queries: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_graph_projector_diagnostics_combines_health_samples_and_rebuild_sources() -> None:
    GraphProjectorDiagnosticsReader, GraphProjectorHealthThresholds = _symbols()

    report = GraphProjectorDiagnosticsReader(FakeConnection()).read(
        thresholds=GraphProjectorHealthThresholds(max_pending_projection_events=5),
        sample_limit=2,
    )

    assert report.health.ok is False
    assert report.health.metrics["projection_events_failed"] == 1
    assert report.health.metrics["graph_fact_batches_dead"] == 1
    assert report.projection_event_samples[0].last_error == "boom"
    assert report.graph_fact_batch_samples[0].fact_count == 7
    assert report.surface_analysis_event_samples[0].last_error == "gds unavailable"
    assert "action_outcomes" in report.rebuild_sources
    assert "python -m graph_projector retry --queue projection_events" in report.suggested_commands()
    assert "python -m graph_projector retry --queue graph_fact_batches" in report.suggested_commands()
    assert "python -m graph_projector process-projection-events" in report.suggested_commands()
    assert "python -m graph_projector retry --queue surface_analysis_events" in report.suggested_commands()


def test_graph_projector_diagnostics_serializes_for_json_output() -> None:
    GraphProjectorDiagnosticsReader, GraphProjectorHealthThresholds = _symbols()

    payload = GraphProjectorDiagnosticsReader(FakeConnection()).read(
        thresholds=GraphProjectorHealthThresholds(max_pending_projection_events=5),
        sample_limit=1,
    ).to_dict()

    assert payload["health"]["status"] == "unhealthy"
    assert payload["projection_event_samples"][0]["source_type"] == "action_outcome"
    assert payload["graph_fact_batch_samples"][0]["parser_version"] == "surface-map-graph-v1"
    assert payload["surface_analysis_event_samples"][0]["event_type"] == "surface_map_projected"
    assert "suggested_commands" in payload


def test_graph_projector_diagnostics_can_filter_program_and_disable_samples() -> None:
    GraphProjectorDiagnosticsReader, _ = _symbols()
    connection = FakeConnection()
    program_id = uuid4()

    report = GraphProjectorDiagnosticsReader(connection).read(program_id=program_id, sample_limit=0)

    assert report.projection_event_samples == ()
    assert report.graph_fact_batch_samples == ()
    assert report.surface_analysis_event_samples == ()
    assert all(parameters.get("program_id") in {program_id, str(program_id)} for parameters in connection.parameters)


def test_graph_projector_diagnostics_rejects_negative_sample_limit() -> None:
    GraphProjectorDiagnosticsReader, _ = _symbols()

    try:
        GraphProjectorDiagnosticsReader(FakeConnection()).read(sample_limit=-1)
    except ValueError as exc:
        assert "sample_limit must be non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected negative sample limit to fail")


def test_graph_projector_cli_exposes_diagnostics_command() -> None:
    source = graph_projector_cli_source()

    assert 'subparsers.add_parser("diagnostics"' in source
    assert "GraphProjectorDiagnosticsReader" in source
    assert "diagnostic_suggested_command" in source
    assert "return 0 if report.health.ok else 1" in source
