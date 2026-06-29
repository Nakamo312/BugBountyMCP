from pathlib import Path
import sys

import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.adapters.orm import raw_artifacts


def test_raw_artifacts_store_preview_and_llm_safety_fields() -> None:
    for column in (
        "preview",
        "sanitized_preview",
        "sanitizer_version",
        "redaction_policy_version",
        "raw_safe_for_llm",
        "sanitized_safe_for_llm",
    ):
        assert column in raw_artifacts.c
    constraint_names = {
        constraint.name
        for constraint in raw_artifacts.constraints
        if constraint.name is not None
    }
    assert "ck_raw_artifacts_sanitized_llm_requires_preview" in constraint_names


def test_preview_migration_extends_current_artifact_schema_head() -> None:
    migration = Path(
        "alembic/versions/i5j6k7l8m9n0_add_artifact_previews.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "h4i5j6k7l8m9"' in migration
    assert '"raw_safe_for_llm"' in migration
    assert '"sanitized_safe_for_llm"' in migration
    assert "raw_safe_for_llm = false" in migration.lower()
    assert "ck_raw_artifacts_sanitized_llm_requires_preview" in migration


def test_search_projection_reads_only_safe_sanitized_artifact_previews() -> None:
    source = Path(
        "services/search-indexer/search_indexer/postgres_reader.py"
    ).read_text(encoding="utf-8")

    assert "sanitized_preview" in source
    assert "sanitized_safe_for_llm = true" in source.lower()
    assert "\n    preview," not in source


def test_artifact_preview_mapping_and_count_exclude_raw_only_artifacts() -> None:
    sys.path.insert(0, str(Path("services/search-indexer").resolve()))
    from search_indexer.postgres_reader import COUNT_SQL
    from search_indexer.reindex import ARTIFACTS_PREVIEW_INDEX, INDEX_MAPPINGS

    properties = INDEX_MAPPINGS[ARTIFACTS_PREVIEW_INDEX]["mappings"]["properties"]

    assert "storage_uri" not in properties
    assert "sanitized_safe_for_llm = true" in COUNT_SQL["artifacts"].lower()
    assert "sanitized_preview is not null" in COUNT_SQL["artifacts"].lower()
