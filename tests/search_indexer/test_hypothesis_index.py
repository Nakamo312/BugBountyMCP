from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.documents import build_hypothesis_document  # noqa: E402
from search_indexer.postgres_reader import COUNT_SQL, HYPOTHESES_SQL  # noqa: E402
from search_indexer.reindex import (  # noqa: E402
    HYPOTHESES_INDEX,
    INDEX_MAPPINGS,
    INDEX_RETENTION_POLICIES,
    TARGETS,
)


def test_hypothesis_index_is_registered_with_static_mapping() -> None:
    assert TARGETS["hypotheses"].index_name == HYPOTHESES_INDEX == "bb-research-hypotheses"

    mapping = INDEX_MAPPINGS[HYPOTHESES_INDEX]["mappings"]
    properties = mapping["properties"]

    assert mapping["dynamic"] is False
    assert properties["schema_version"] == {"type": "keyword"}
    assert properties["sanitizer_version"] == {"type": "keyword"}
    assert properties["program_id"] == {"type": "keyword"}
    assert properties["hypothesis_type"] == {"type": "keyword"}
    assert properties["status"] == {"type": "keyword"}
    assert properties["safe_evidence_text"] == {"type": "text"}
    assert HYPOTHESES_INDEX in INDEX_RETENTION_POLICIES


def test_hypothesis_sql_reads_canonical_tables_and_redacts_unsafe_evidence() -> None:
    assert "FROM research_hypotheses rh" in HYPOTHESES_SQL
    assert "LEFT JOIN research_hypothesis_evidence rhe" in HYPOTHESES_SQL
    assert "rh.program_id = %s::uuid" in HYPOTHESES_SQL
    assert "CASE WHEN rhe.safe_for_search THEN rhe.claim ELSE NULL END" in HYPOTHESES_SQL
    assert "CASE WHEN rhe.safe_for_search THEN rhe.safe_excerpt ELSE NULL END" in HYPOTHESES_SQL
    assert COUNT_SQL["hypotheses"] == "SELECT count(*) FROM research_hypotheses WHERE program_id = %s::uuid"


def test_hypothesis_document_indexes_only_search_safe_evidence_text() -> None:
    document = build_hypothesis_document(
        {
            "id": "hyp-1",
            "program_id": "program-1",
            "hypothesis_type": "search_surface_followup",
            "hypothesis_fingerprint": "fingerprint-1",
            "status": "needs_verification",
            "state_version": 2,
            "priority_score": 80,
            "confidence": 0.7,
            "severity_guess": "medium",
            "safety_level": "passive",
            "score_version": "hypothesis-builder-v1",
            "inputs_hash": "inputs-1",
            "source_signal_fingerprints": ["signal-1", "signal-1", "signal-2"],
            "evidence_count": 2,
            "updated_at": "2026-06-24T12:00:00+00:00",
            "evidence": [
                {
                    "ref_type": "search",
                    "ref_id": "search-1",
                    "role": "primary",
                    "claim_type": "safe_claim",
                    "claim": "Search projection shows token=secret-value in a URL.",
                    "safe_excerpt": "token=secret-value",
                    "safe_for_search": True,
                },
                {
                    "ref_type": "artifact",
                    "ref_id": "artifact-1",
                    "role": "supporting",
                    "claim_type": "unsafe_claim",
                    "claim": "Authorization: Bearer should-not-index",
                    "safe_excerpt": "should-not-index",
                    "safe_for_search": False,
                },
            ],
        }
    )

    assert document["id"] == "hyp-1"
    assert document["hypothesis_id"] == "hyp-1"
    assert document["program_id"] == "program-1"
    assert document["source_signal_fingerprints"] == ["signal-1", "signal-2"]
    assert document["evidence_ref_types"] == ["search", "artifact"]
    assert document["evidence_roles"] == ["primary", "supporting"]
    assert document["evidence_claim_types"] == ["safe_claim", "unsafe_claim"]
    assert document["evidence_ref_ids"] == ["search-1", "artifact-1"]
    assert document["safe_evidence_text"] == [
        "Search projection shows token=[redacted] in a URL.",
        "token=[redacted]",
    ]
    assert "should-not-index" not in str(document)
    assert "secret-value" not in str(document)
