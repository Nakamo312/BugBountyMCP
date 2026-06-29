from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.retry import GraphProjectorRetryService

    return GraphProjectorRetryService


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
        if "UPDATE graph_projection_events" in self.query:
            return [{"id": uuid4()}, {"id": uuid4()}]
        if "UPDATE graph_fact_batches" in self.query:
            return [{"id": uuid4()}]
        if "UPDATE surface_component_analysis_events" in self.query:
            return [{"id": uuid4()}, {"id": uuid4()}, {"id": uuid4()}]
        raise AssertionError(f"unexpected query: {self.query}")


class FakeConnection:
    def __init__(self) -> None:
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


def test_graph_projector_retry_resets_failed_dead_projection_events_and_batches() -> None:
    GraphProjectorRetryService = _symbols()
    connection = FakeConnection()

    result = GraphProjectorRetryService(connection).retry(limit=25)

    assert result.projection_events_reset == 2
    assert result.graph_fact_batches_reset == 1
    assert result.surface_analysis_events_reset == 3
    assert result.total_reset == 6
    assert connection.commits == 3
    assert any("FROM graph_projection_events" in query for query in connection.queries)
    assert any("FROM graph_fact_batches" in query for query in connection.queries)
    assert any("FROM surface_component_analysis_events" in query for query in connection.queries)
    assert all(parameters["statuses"] == ["failed", "dead"] for parameters in connection.parameters)
    assert all(parameters["limit"] == 25 for parameters in connection.parameters)
    assert all("status <> 'locked' OR locked_until IS NULL OR locked_until < %(now)s" in query for query in connection.queries)


def test_graph_projector_retry_can_target_queue_status_and_program() -> None:
    GraphProjectorRetryService = _symbols()
    connection = FakeConnection()
    program_id = uuid4()

    result = GraphProjectorRetryService(connection).retry(
        queues=["projection_events"],
        statuses=["locked"],
        limit=7,
        program_id=program_id,
    )

    assert result.projection_events_reset == 2
    assert result.graph_fact_batches_reset == 0
    assert len(connection.queries) == 1
    assert "UPDATE graph_projection_events" in connection.queries[0]
    assert connection.parameters[0]["statuses"] == ["locked"]
    assert connection.parameters[0]["program_id"] == str(program_id)
    assert connection.parameters[0]["limit"] == 7


def test_graph_projector_retry_rejects_invalid_inputs() -> None:
    GraphProjectorRetryService = _symbols()
    service = GraphProjectorRetryService(FakeConnection())

    try:
        service.retry(limit=0)
    except ValueError as exc:
        assert "limit must be positive" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid limit to fail")

    try:
        service.retry(queues=["nope"])
    except ValueError as exc:
        assert "unsupported retry queue" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid queue to fail")

    try:
        service.retry(statuses=["processed"])
    except ValueError as exc:
        assert "unsupported retry status" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected invalid status to fail")


def test_graph_projector_cli_exposes_retry_command() -> None:
    source = graph_projector_cli_source()

    assert 'subparsers.add_parser("retry"' in source
    assert "GraphProjectorRetryService" in source
    assert "GRAPH_PROJECTOR_RETRY_QUEUES" in source
    assert "projection_events_reset" in source
    assert "graph_fact_batches_reset" in source
    assert "surface_analysis_events_reset" in source


def test_graph_projector_retry_queries_are_static_and_bounded() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.retry import (
        _RESET_GRAPH_FACT_BATCHES,
        _RESET_GRAPH_PROJECTION_EVENTS,
        _RESET_SURFACE_COMPONENT_ANALYSIS_EVENTS,
    )

    statements = (
        _RESET_GRAPH_PROJECTION_EVENTS,
        _RESET_GRAPH_FACT_BATCHES,
        _RESET_SURFACE_COMPONENT_ANALYSIS_EVENTS,
    )
    assert all("WITH retry_rows AS" in statement for statement in statements)
    assert all("status = ANY(%(statuses)s)" in statement for statement in statements)
    assert all("%(program_id)s IS NULL OR program_id = %(program_id)s" in statement for statement in statements)
    assert all("{program" not in statement for statement in statements)
    assert all("{table" not in statement for statement in statements)
    assert all("RETURNING id" in statement for statement in statements)
    assert "processed_at = NULL" in _RESET_GRAPH_PROJECTION_EVENTS
    assert "applied_at = NULL" in _RESET_GRAPH_FACT_BATCHES
    assert "processed_at = NULL" in _RESET_SURFACE_COMPONENT_ANALYSIS_EVENTS
