from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.adapters.orm import (
    http_observations,
    javascript_references,
    raw_artifacts,
)


def test_raw_artifacts_store_explicit_lineage_fields() -> None:
    for column in (
        "parser_name",
        "parser_version",
        "scope_decision_id",
        "source_targets",
        "parent_artifact_id",
    ):
        assert column in raw_artifacts.c

    assert raw_artifacts.c.scope_decision_id.foreign_keys
    assert raw_artifacts.c.parent_artifact_id.foreign_keys


def test_artifact_lineage_migration_extends_current_head() -> None:
    migration = Path(
        "alembic/versions/j6k7l8m9n0o1_add_artifact_lineage.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "i5j6k7l8m9n0"' in migration
    assert '"parser_version"' in migration
    assert '"scope_decision_id"' in migration
    assert '"source_targets"' in migration
    assert '"parent_artifact_id"' in migration
    assert "raw_artifacts_parent_artifact_id_fkey" in migration


def test_parser_outputs_and_sanitized_preview_link_to_raw_artifact() -> None:
    assert http_observations.c.raw_artifact_id.foreign_keys
    assert javascript_references.c.raw_artifact_id.foreign_keys
    assert "sanitized_preview" in raw_artifacts.c
    assert "sanitizer_version" in raw_artifacts.c
