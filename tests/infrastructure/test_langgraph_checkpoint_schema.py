from __future__ import annotations

from pathlib import Path


def test_langgraph_postgres_checkpoint_migration_owns_required_tables() -> None:
    migration = Path(
        "alembic/versions/f2g3h4i5j6k7_add_langgraph_checkpoints.py"
    ).read_text(encoding="utf-8")

    assert "down_revision = 'e1f2g3h4i5j6'" in migration
    for table in (
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    ):
        assert f"op.create_table('{table}'" in migration
    assert "task_path" in migration
    assert "range(10)" in migration


def test_di_uses_durable_postgres_checkpointer_without_runtime_schema_setup() -> None:
    source = Path("src/api/application/di.py").read_text(encoding="utf-8")

    assert "AsyncPostgresSaver.from_conn_string" in source
    assert "yield checkpointer" in source
    assert "checkpointer.setup" not in source
