from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.documents import (  # noqa: E402
    build_surface_component_document,
    build_surface_delta_document,
)
from search_indexer.postgres_reader import (  # noqa: E402
    SURFACE_COMPONENT_ANALYSIS_SQL,
    SURFACE_DELTAS_SQL,
)
from search_indexer.reindex import (  # noqa: E402
    INDEX_MAPPINGS,
    SURFACE_COMPONENTS_INDEX,
    SURFACE_DELTAS_INDEX,
    TARGETS,
    build_reindex_filters,
)


def test_surface_component_and_delta_indexes_are_registered() -> None:
    assert TARGETS["surface-components"].index_name == SURFACE_COMPONENTS_INDEX == "bb-surface-components"
    assert TARGETS["surface-deltas"].index_name == SURFACE_DELTAS_INDEX == "bb-surface-deltas"

    for index_name in (SURFACE_COMPONENTS_INDEX, SURFACE_DELTAS_INDEX):
        mapping = INDEX_MAPPINGS[index_name]["mappings"]
        assert mapping["dynamic"] is False
        assert mapping["properties"]["schema_version"] == {"type": "keyword"}
        assert mapping["properties"]["sanitizer_version"] == {"type": "keyword"}
        assert mapping["properties"]["program_id"] == {"type": "keyword"}


def test_surface_component_and_delta_sql_are_program_scoped_reads() -> None:
    assert "FROM surface_component_analysis_items item" in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "JOIN surface_component_analysis_runs run" in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "item.program_id = %s::uuid" in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "item.analysis_run_id = %s::uuid" in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "item.snapshot_id = %s::uuid" in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "FROM surface_deltas" in SURFACE_DELTAS_SQL
    assert "program_id = %s::uuid" in SURFACE_DELTAS_SQL
    assert "to_snapshot_id = %s::uuid" in SURFACE_DELTAS_SQL
    assert "raw_artifacts" not in SURFACE_COMPONENT_ANALYSIS_SQL
    assert "raw_artifacts" not in SURFACE_DELTAS_SQL


def test_surface_component_document_is_bounded_and_review_safe() -> None:
    document = build_surface_component_document(
        {
            "id": "item-1",
            "analysis_run_id": "analysis-run-1",
            "program_id": "program-1",
            "snapshot_id": "snapshot-1",
            "previous_snapshot_id": "snapshot-0",
            "algorithm": "surface-component-report",
            "algorithm_version": "1",
            "report_fingerprint": "abc123",
            "component_id": 7,
            "node_count": 10,
            "changed_node_count": 2,
            "structural_pressure_score": 80,
            "exploration_priority_score": 75,
            "action_candidate_count": 1,
            "metrics_json": {"token": "secret-token", "safe": "ok"},
            "action_candidates_json": [
                {"capability_id": "httpx", "profile_id": "safe", "reason": "x" * 20_000}
            ],
            "created_at": "2026-06-27T00:00:00+00:00",
        }
    )

    assert document["id"] == "item-1"
    assert document["program_id"] == "program-1"
    assert document["component_id"] == 7
    assert document["metrics"]["token"] == "[redacted]"
    assert "secret-token" not in str(document)
    assert len(document["action_candidates"][0]["reason"]) <= 8_192


def test_surface_delta_document_is_bounded_and_sanitized() -> None:
    document = build_surface_delta_document(
        {
            "id": "delta-1",
            "program_id": "program-1",
            "from_snapshot_id": "snapshot-0",
            "to_snapshot_id": "snapshot-1",
            "delta_type": "node_introduced",
            "subject_type": "endpoint",
            "subject_fingerprint": "fingerprint-1",
            "novelty_score": 67,
            "details_json": {"api_key": "secret", "path": "/a"},
            "created_at": "2026-06-27T00:00:00+00:00",
        }
    )

    assert document["id"] == "delta-1"
    assert document["to_snapshot_id"] == "snapshot-1"
    assert document["details"]["api_key"] == "[redacted]"
    assert "secret" not in str(document)


def test_surface_incremental_reindex_filter_validation() -> None:
    assert build_reindex_filters(
        target="surface-components",
        analysis_run_id="run-1",
        snapshot_id="snapshot-1",
    ) == {"analysis_run_id": "run-1", "snapshot_id": "snapshot-1"}
    assert build_reindex_filters(
        target="surface-deltas",
        analysis_run_id=None,
        snapshot_id="snapshot-1",
    ) == {"snapshot_id": "snapshot-1"}

    try:
        build_reindex_filters(target="http-observations", analysis_run_id="run-1", snapshot_id=None)
    except ValueError as exc:
        assert "--analysis-run-id" in str(exc)
    else:
        raise AssertionError("expected invalid analysis-run-id target")

    try:
        build_reindex_filters(target="all", analysis_run_id=None, snapshot_id="snapshot-1")
    except ValueError as exc:
        assert "--snapshot-id" in str(exc)
    else:
        raise AssertionError("expected invalid snapshot target")
