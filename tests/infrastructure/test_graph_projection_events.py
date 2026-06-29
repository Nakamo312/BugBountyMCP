from __future__ import annotations

from pathlib import Path


def test_graph_projection_events_table_is_declared_as_durable_queue() -> None:
    source = Path("src/api/infrastructure/adapters/orm_tables/graph_projection.py").read_text(encoding="utf-8")

    assert "graph_projection_events = Table(" in source
    for column in [
        "'program_id'",
        "'source_type'",
        "'source_id'",
        "'event_type'",
        "'dedupe_key'",
        "'status'",
        "'attempts'",
        "'available_at'",
        "'locked_by'",
        "'locked_until'",
        "'processed_at'",
        "'last_error'",
    ]:
        assert column in source

    assert "idx_graph_projection_events_status_available" in source
    assert "idx_graph_projection_events_source" in source
    assert "uq_graph_projection_events_dedupe_key" in source
    assert "ck_graph_projection_events_status_valid" in source


def test_graph_projection_events_migration_adds_raw_artifact_trigger() -> None:
    migration = Path("alembic/versions/b8c9d0e1f2g3_add_graph_projection_events.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "a7b8c9d0e1f2"' in source
    assert "graph_projection_events" in source
    assert "enqueue_raw_artifact_graph_projection_event" in source
    assert "CREATE TRIGGER raw_artifacts_graph_projection_event" in source
    assert "AFTER INSERT ON raw_artifacts" in source
    assert "raw_artifact_created" in source
    assert "NEW.run_id IS NULL" in source


def test_graph_projection_events_have_table_level_notify_trigger_for_all_event_types() -> None:
    migration = Path("alembic/versions/b8c9d0e1f2g4_add_graph_projection_event_notifications.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "a7b8c9d0e1f3"' in source
    assert "notify_graph_projection_event_changed" in source
    assert "CREATE TRIGGER graph_projection_events_notify_insert" in source
    assert "AFTER INSERT ON graph_projection_events" in source
    assert "CREATE TRIGGER graph_projection_events_notify_status" in source
    assert "AFTER UPDATE OF status, available_at ON graph_projection_events" in source
    assert "pg_notify('graph_projection_events_changed'" in source
    assert "NEW.dedupe_key" in source


def test_graph_projection_events_contract_includes_http_observations_ready() -> None:
    source = Path("src/api/infrastructure/repositories/adapters/http_observation.py").read_text(
        encoding="utf-8"
    )

    assert "graph_projection_events" in source
    assert "http_observations_ready" in source
    assert "source_type=\"raw_artifact\"" in source
    assert "http-observations-ready:" in source
    assert "on_conflict_do_nothing(index_elements=[\"dedupe_key\"])" in source
