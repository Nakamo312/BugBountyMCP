from __future__ import annotations

from uuid import uuid4


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append((query, parameters or {}))


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_obj = RecordingCursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


def _writer_symbols():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.projection_event_state import ProjectionEventStateWriter

    return ProjectionEventStateWriter


def test_projection_event_state_writer_marks_processed_with_worker_lease_guard() -> None:
    ProjectionEventStateWriter = _writer_symbols()
    connection = RecordingConnection()
    event_id = uuid4()

    ProjectionEventStateWriter(connection, worker_id="worker-1").mark_processed(event_id)

    query, parameters = connection.cursor_obj.calls[0]
    assert "UPDATE graph_projection_events" in query
    assert "status = 'processed'" in query
    assert "status = 'locked'" in query
    assert "locked_by = %(worker_id)s" in query
    assert parameters["event_id"] == event_id
    assert parameters["worker_id"] == "worker-1"
    assert connection.commits == 1


def test_projection_event_state_writer_marks_failure_with_dead_status_and_bounded_error() -> None:
    ProjectionEventStateWriter = _writer_symbols()
    connection = RecordingConnection()
    event_id = uuid4()

    ProjectionEventStateWriter(connection, worker_id="worker-2").mark_failed(
        event_id,
        error="x" * 20,
        dead=True,
        max_error_chars=7,
    )

    query, parameters = connection.cursor_obj.calls[0]
    assert "UPDATE graph_projection_events" in query
    assert "status = %(status)s" in query
    assert "status = 'locked'" in query
    assert "locked_by = %(worker_id)s" in query
    assert parameters["event_id"] == event_id
    assert parameters["status"] == "dead"
    assert parameters["error"] == "x" * 7
    assert parameters["worker_id"] == "worker-2"
    assert connection.commits == 1


def test_projection_event_producers_delegate_state_transitions_to_shared_writer() -> None:
    from pathlib import Path

    producer_sources = [
        Path("services/graph-projector/graph_projector/producers/raw_artifacts.py"),
        Path("services/graph-projector/graph_projector/producers/http_observations.py"),
        Path("services/graph-projector/graph_projector/producers/javascript_references.py"),
        Path("services/graph-projector/graph_projector/producers/action_outcomes.py"),
    ]

    for path in producer_sources:
        source = path.read_text(encoding="utf-8")
        assert "ProjectionEventStateWriter" in source
        assert "def _mark_projection_event_processed" not in source
        assert "def _mark_projection_event_failed" not in source
