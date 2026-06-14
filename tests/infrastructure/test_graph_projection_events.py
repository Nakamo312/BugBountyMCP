from __future__ import annotations

from pathlib import Path


def test_graph_projection_events_table_is_declared_as_durable_queue() -> None:
    source = Path("src/api/infrastructure/adapters/orm.py").read_text(encoding="utf-8")

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


def test_graph_projection_events_migration_adds_raw_artifact_trigger_and_notify() -> None:
    migration = Path("alembic/versions/b8c9d0e1f2g3_add_graph_projection_events.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "a7b8c9d0e1f2"' in source
    assert "graph_projection_events" in source
    assert "enqueue_raw_artifact_graph_projection_event" in source
    assert "CREATE TRIGGER raw_artifacts_graph_projection_event" in source
    assert "AFTER INSERT ON raw_artifacts" in source
    assert "pg_notify('graph_projection_events_changed'" in source
    assert "raw_artifact_created" in source
    assert "NEW.run_id IS NULL" in source
