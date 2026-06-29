from __future__ import annotations

from pathlib import Path


def test_projection_watermarks_are_declared_in_orm() -> None:
    source = Path("src/api/infrastructure/adapters/orm_tables/graph_projection.py").read_text(encoding="utf-8")

    assert "projection_watermarks = Table(" in source
    for column in (
        "'program_id'",
        "'projection_type'",
        "'projection_name'",
        "'source_watermark'",
        "'applied_watermark'",
        "'lag_count'",
        "'status'",
        "'last_error'",
        "'observed_at'",
        "'applied_at'",
    ):
        assert column in source
    assert "uq_projection_watermarks_program_projection" in source
    assert "ck_projection_watermarks_ready_consistent" in source


def test_projection_watermarks_migration_follows_current_head() -> None:
    migration = Path("alembic/versions/c9d0e1f2g3h5_add_projection_watermarks.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "b8c9d0e1f2g4"' in source
    assert '"projection_watermarks"' in source
    assert "uq_projection_watermarks_program_projection" in source
    assert "lag_count >= 0" in source
    assert "status IN ('observed', 'running', 'ready', 'failed')" in source
    assert "status != 'ready' OR (lag_count = 0 AND source_watermark = applied_watermark)" in source


def test_projection_watermarks_migration_observes_current_opensearch_sources() -> None:
    source = Path(
        "alembic/versions/c9d0e1f2g3h5_add_projection_watermarks.py"
    ).read_text(encoding="utf-8")

    assert "mark_opensearch_projection_observed" in source
    assert "AFTER INSERT OR UPDATE OR DELETE ON {table_name}" in source
    for table, projection in (
        ("http_observations", "http-observations"),
        ("raw_artifacts", "artifacts"),
        ("findings", "findings"),
        ("event_store", "detection-signals"),
    ):
        assert f'("{table}", "{projection}")' in source
    assert "lag_count = projection_watermarks.lag_count + 1" in source
    assert "status = 'observed'" in source
