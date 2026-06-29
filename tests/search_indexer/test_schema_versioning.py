from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.documents import (  # noqa: E402
    SANITIZER_VERSION,
    SCHEMA_VERSION,
    build_artifact_preview_document,
    build_detection_signal_document,
    build_finding_document,
    build_http_observation_document,
    build_hypothesis_document,
    build_surface_component_document,
    build_surface_delta_document,
)
from search_indexer.reindex import INDEX_MAPPINGS  # noqa: E402


def test_all_search_documents_carry_schema_and_sanitizer_versions() -> None:
    builders = (
        build_http_observation_document,
        build_artifact_preview_document,
        build_finding_document,
        build_detection_signal_document,
        build_hypothesis_document,
        build_surface_component_document,
        build_surface_delta_document,
    )

    for builder in builders:
        document = builder({"id": "document-1", "program_id": "program-1"})

        assert document["schema_version"] == SCHEMA_VERSION
        assert document["sanitizer_version"] == SANITIZER_VERSION
        assert document["program_id"] == "program-1"


def test_artifact_preview_document_uses_only_persisted_sanitized_preview() -> None:
    document = build_artifact_preview_document(
        {
            "id": "artifact-1",
            "program_id": "program-1",
            "preview": "Authorization: Bearer secret",
            "sanitized_preview": "Authorization: [redacted]",
            "sanitizer_version": "research-sanitizer-v1",
            "sanitized_safe_for_llm": True,
            "storage_uri": "data/raw/secret.ndjson",
        }
    )

    assert document["preview"] == "Authorization: [redacted]"
    assert document["sanitizer_version"] == "research-sanitizer-v1"
    assert "secret" not in str(document)
    assert "storage_uri" not in document


def test_all_search_index_mappings_declare_version_fields() -> None:
    for mapping in INDEX_MAPPINGS.values():
        properties = mapping["mappings"]["properties"]

        assert properties["schema_version"] == {"type": "keyword"}
        assert properties["sanitizer_version"] == {"type": "keyword"}


def test_relevant_documents_expose_canonical_artifact_and_tool_run_ids() -> None:
    http_document = build_http_observation_document(
        {
            "id": "observation-1",
            "program_id": "program-1",
            "raw_artifact_id": "artifact-1",
            "run_id": "run-1",
        }
    )
    artifact_document = build_artifact_preview_document(
        {
            "id": "artifact-1",
            "program_id": "program-1",
            "run_id": "run-1",
        }
    )

    assert http_document["artifact_id"] == "artifact-1"
    assert http_document["tool_run_id"] == "run-1"
    assert artifact_document["artifact_id"] == "artifact-1"
    assert artifact_document["tool_run_id"] == "run-1"
