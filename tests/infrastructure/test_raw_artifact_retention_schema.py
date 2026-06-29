from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.adapters.orm import raw_artifacts


def test_raw_artifacts_store_queryable_compression_and_retention_fields() -> None:
    assert "content_encoding" in raw_artifacts.c
    assert "retention_class" in raw_artifacts.c
    assert "storage_size_bytes" in raw_artifacts.c
    assert any(
        index.name == "idx_raw_artifacts_retention_class"
        for index in raw_artifacts.indexes
    )


def test_retention_migration_extends_raw_artifacts_from_current_head() -> None:
    migration = Path(
        "alembic/versions/h4i5j6k7l8m9_add_artifact_compression_retention.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "g3h4i5j6k7l8"' in migration
    assert '"content_encoding"' in migration
    assert '"retention_class"' in migration
    assert '"storage_size_bytes"' in migration
    assert "idx_raw_artifacts_retention_class" in migration
