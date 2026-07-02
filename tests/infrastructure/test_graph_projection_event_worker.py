from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.projection_events import GraphProjectionEventWorker, ProjectionEventWorkerResult

    return GraphProjectionEventWorker, ProjectionEventWorkerResult


class FakeEnqueuer:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []

    def enqueue_pending(self, *, limit: int, program_id=None):
        self.calls.append((limit, program_id))
        return self.results.pop(0)


def test_projection_event_worker_dispatches_supported_event_types_without_dedicated_services() -> None:
    GraphProjectionEventWorker, ProjectionEventWorkerResult = _symbols()
    program_id = uuid4()
    raw = FakeEnqueuer([ProjectionEventWorkerResult(scanned=1, enqueued=1)])
    http = FakeEnqueuer([ProjectionEventWorkerResult(scanned=1, skipped=1)])
    javascript = FakeEnqueuer([ProjectionEventWorkerResult(scanned=2, enqueued=2)])
    action_outcomes = FakeEnqueuer([ProjectionEventWorkerResult(scanned=1, enqueued=1)])

    result = GraphProjectionEventWorker(
        raw_artifact_enqueuer=raw,
        http_observation_enqueuer=http,
        javascript_reference_enqueuer=javascript,
        action_outcome_enqueuer=action_outcomes,
    ).process_once(limit=25, program_id=program_id)

    assert result.scanned == 5
    assert result.enqueued == 4
    assert result.skipped == 1
    assert raw.calls == [(25, program_id)]
    assert http.calls == [(25, program_id)]
    assert javascript.calls == [(25, program_id)]
    assert action_outcomes.calls == [(25, program_id)]


def test_projection_event_worker_loop_stops_after_idle_threshold() -> None:
    GraphProjectionEventWorker, ProjectionEventWorkerResult = _symbols()
    active = ProjectionEventWorkerResult(scanned=1, enqueued=1)
    idle = ProjectionEventWorkerResult()
    raw = FakeEnqueuer([active, idle, idle])
    http = FakeEnqueuer([idle, idle, idle])
    javascript = FakeEnqueuer([idle, idle, idle])
    sleeps = []

    result = GraphProjectionEventWorker(
        raw_artifact_enqueuer=raw,
        http_observation_enqueuer=http,
        javascript_reference_enqueuer=javascript,
    ).process_loop(
        limit=10,
        max_iterations=3,
        idle_exit_after=2,
        poll_seconds=0.5,
        sleep=sleeps.append,
    )

    assert result.scanned == 1
    assert result.enqueued == 1
    assert result.empty == 2
    assert result.iterations == 3
    assert sleeps == [0.5]


def test_projection_event_worker_is_wired_into_graph_compose_profile() -> None:
    main_source = graph_projector_cli_source()
    compose_source = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("process-projection-events"' in main_source
    assert 'subparsers.add_parser("process-projection-events-loop"' in main_source
    assert 'subparsers.add_parser("enqueue-action-outcomes"' in main_source
    assert "ActionOutcomeGraphFactEnqueuer" in main_source
    assert "GraphProjectionEventWorker" in main_source
    assert "graph-projector-events:" in compose_source
    assert "container_name: bb-graph-projector-events" in compose_source
    assert 'command: ["process-projection-events-loop", "--bootstrap-rebuild"]' in compose_source
    assert "--bootstrap-rebuild" in main_source
    assert "GRAPH_BOOTSTRAP_REBUILD_LIMIT" in compose_source
    assert "GRAPH_PROJECTION_EVENT_NOTIFY_CHANNEL" in compose_source
