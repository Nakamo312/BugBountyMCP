from __future__ import annotations

from dataclasses import dataclass

import pytest
from uuid import UUID, uuid4

import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer import events  # noqa: E402
from search_indexer.events import (  # noqa: E402
    ClaimedSearchProjectionEvent,
    SearchProjectionEvent,
    SearchProjectionEventStore,
    SearchProjectionEventWorker,
)
from search_indexer.reindex import build_parser  # noqa: E402


@dataclass
class FakeSettings:
    postgres_dsn: str = "postgres://example"
    opensearch_url: str = "http://opensearch:9200"
    opensearch_timeout_seconds: float = 5.0
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_verify_certs: bool = False


class FakeEventStore:
    def __init__(self, claimed: ClaimedSearchProjectionEvent | None) -> None:
        self.claimed = claimed
        self.processed: tuple[UUID, int, str] | None = None
        self.failed: tuple[UUID, str, bool, str] | None = None

    def claim_next(self, **_kwargs):
        claimed = self.claimed
        self.claimed = None
        return claimed

    def mark_processed(self, event_id: UUID, *, indexed_count: int, worker_id: str) -> None:
        self.processed = (event_id, indexed_count, worker_id)

    def mark_failed(self, event_id: UUID, *, error: str, dead: bool, worker_id: str) -> None:
        self.failed = (event_id, error, dead, worker_id)


def test_search_projection_event_dedupe_key_is_filter_stable() -> None:
    first = events._dedupe_key(
        program_id="program-1",
        target="surface-components",
        source_type="surface_component_analysis_run",
        source_id="run-1",
        filters={"snapshot_id": "snapshot-1", "analysis_run_id": "run-1"},
    )
    second = events._dedupe_key(
        program_id="program-1",
        target="surface-components",
        source_type="surface_component_analysis_run",
        source_id="run-1",
        filters={"analysis_run_id": "run-1", "snapshot_id": "snapshot-1"},
    )
    assert first == second
    assert first.startswith("search-projection:program-1:surface-components:")


def test_search_projection_event_worker_processes_incremental_reindex(monkeypatch) -> None:
    event_id = uuid4()
    claimed = ClaimedSearchProjectionEvent(
        event=SearchProjectionEvent(
            id=event_id,
            program_id="program-1",
            target="surface-components",
            source_type="surface_component_analysis_run",
            source_id="run-1",
            filters_json={"analysis_run_id": "run-1"},
            attempts=1,
        ),
        attempts=1,
    )
    store = FakeEventStore(claimed)
    calls = []

    def fake_run_reindex(**kwargs):
        calls.append(kwargs)
        return {"surface-components": 3}

    monkeypatch.setattr(events, "run_reindex", fake_run_reindex)

    worker = SearchProjectionEventWorker(
        settings=FakeSettings(),
        event_store=store,  # type: ignore[arg-type]
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=5,
        limit=100,
        batch_size=50,
    )
    result = worker.process_one(program_id="program-1", target="surface-components")

    assert result.status == "processed"
    assert result.indexed_count == 3
    assert store.processed == (event_id, 3, "worker-1")
    assert calls[0]["target"] == "surface-components"
    assert calls[0]["filters"] == {"analysis_run_id": "run-1"}


def test_search_projection_event_worker_marks_failed_without_dead_until_max_attempts(monkeypatch) -> None:
    event_id = uuid4()
    store = FakeEventStore(
        ClaimedSearchProjectionEvent(
            event=SearchProjectionEvent(
                id=event_id,
                program_id="program-1",
                target="surface-deltas",
                source_type="surface_snapshot",
                source_id="snapshot-1",
                filters_json={"snapshot_id": "snapshot-1"},
                attempts=1,
            ),
            attempts=1,
        )
    )

    def fake_run_reindex(**_kwargs):
        raise RuntimeError("opensearch unavailable")

    monkeypatch.setattr(events, "run_reindex", fake_run_reindex)
    worker = SearchProjectionEventWorker(
        settings=FakeSettings(),
        event_store=store,  # type: ignore[arg-type]
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=5,
        limit=100,
        batch_size=50,
    )

    result = worker.process_one()

    assert result.status == "failed"
    assert store.failed is not None
    assert store.failed[0] == event_id
    assert store.failed[2] is False
    assert store.failed[3] == "worker-1"


def test_search_indexer_cli_registers_event_processing_commands() -> None:
    parser = build_parser()
    args = parser.parse_args(["process-events", "--target", "surface-components", "--limit", "10"])
    assert args.command == "process-events"
    assert args.target == "surface-components"
    assert args.limit == 10

    loop_args = parser.parse_args(["process-events-loop", "--target", "surface-deltas", "--max-events", "3"])
    assert loop_args.command == "process-events-loop"
    assert loop_args.target == "surface-deltas"
    assert loop_args.max_events == 3


def test_search_projection_events_migration_declares_durable_queue() -> None:
    migration = Path("alembic/versions/d7e8f9a0b1c2_search_projection_events.py").read_text()
    assert '"search_projection_events"' in migration
    assert "uq_search_projection_events_dedupe_key" in migration
    assert "FOR UPDATE SKIP LOCKED" not in migration
    assert "status IN ('pending', 'locked', 'processed', 'failed', 'dead')" in migration


def test_search_projection_event_enqueue_statement_is_static_and_bounded() -> None:
    keep_existing = events._enqueue_statement(reset_existing=False)
    reset_existing = events._enqueue_statement(reset_existing=True)

    assert "ON CONFLICT (dedupe_key) DO UPDATE" in keep_existing
    assert "SET updated_at = search_projection_events.updated_at" in keep_existing
    assert "EXCLUDED.filters_json" not in keep_existing

    assert "ON CONFLICT (dedupe_key) DO UPDATE" in reset_existing
    assert "SET filters_json = EXCLUDED.filters_json" in reset_existing
    assert "status = 'pending'" in reset_existing
    assert "locked_by = NULL" in reset_existing
    assert "RETURNING id" in reset_existing

    assert "{" not in keep_existing
    assert "}" not in keep_existing
    assert "{" not in reset_existing.replace("{}", "")
    assert "}" not in reset_existing.replace("{}", "")


def test_search_projection_event_state_transitions_use_worker_lease_guard() -> None:
    processed_source = SearchProjectionEventStore.mark_processed.__code__.co_consts
    failed_source = SearchProjectionEventStore.mark_failed.__code__.co_consts
    processed_sql = next(value for value in processed_source if isinstance(value, str) and "UPDATE search_projection_events" in value)
    failed_sql = next(value for value in failed_source if isinstance(value, str) and "UPDATE search_projection_events" in value)

    assert "AND status = 'locked'" in processed_sql
    assert "AND locked_by = %s" in processed_sql
    assert "AND status = 'locked'" in failed_sql
    assert "AND locked_by = %s" in failed_sql


def test_search_projection_event_contract_rejects_unknown_target_and_source_type() -> None:
    with pytest.raises(ValueError, match="unsupported surface projection event target"):
        SearchProjectionEventStore("postgres://example").enqueue(
            program_id="00000000-0000-0000-0000-000000000001",
            target="http-observations",
            source_type="http_observation",
        )

    with pytest.raises(ValueError, match="unsupported source_type"):
        SearchProjectionEventStore("postgres://example").enqueue(
            program_id="00000000-0000-0000-0000-000000000001",
            target="surface-components",
            source_type="surface_snapshot",
        )


def test_search_projection_event_contract_rejects_filters_outside_target_contract() -> None:
    with pytest.raises(ValueError, match="unsupported filter"):
        SearchProjectionEventStore("postgres://example").enqueue(
            program_id="00000000-0000-0000-0000-000000000001",
            target="surface-deltas",
            source_type="surface_snapshot",
            filters_json={"analysis_run_id": "run-1"},
        )


def test_search_projection_worker_rejects_non_event_targets_before_claiming() -> None:
    store = FakeEventStore(None)
    worker = SearchProjectionEventWorker(
        settings=FakeSettings(),
        event_store=store,  # type: ignore[arg-type]
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=5,
        limit=100,
        batch_size=50,
    )

    with pytest.raises(ValueError, match="unsupported surface projection event target"):
        worker.process_one(target="http-observations")
