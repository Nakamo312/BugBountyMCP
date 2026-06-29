from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.documents import (  # noqa: E402
    build_endpoint_document,
    build_technology_document,
)
from search_indexer.postgres_reader import (  # noqa: E402
    ENDPOINTS_SQL,
    TECHNOLOGIES_SQL,
)
from search_indexer.reindex import (  # noqa: E402
    ENDPOINTS_INDEX,
    INDEX_MAPPINGS,
    TARGETS,
    TECHNOLOGIES_INDEX,
)


def test_endpoint_and_technology_indexes_have_static_versioned_mappings() -> None:
    assert TARGETS["endpoints"].index_name == ENDPOINTS_INDEX == "bb-endpoints"
    assert TARGETS["technologies"].index_name == TECHNOLOGIES_INDEX == "bb-technologies"

    for index_name in (ENDPOINTS_INDEX, TECHNOLOGIES_INDEX):
        mapping = INDEX_MAPPINGS[index_name]["mappings"]
        assert mapping["dynamic"] is False
        assert mapping["properties"]["schema_version"] == {"type": "keyword"}
        assert mapping["properties"]["sanitizer_version"] == {"type": "keyword"}
        assert mapping["properties"]["program_id"] == {"type": "keyword"}


def test_endpoint_and_technology_sql_are_program_scoped_canonical_reads() -> None:
    assert "FROM endpoints e" in ENDPOINTS_SQL
    assert "JOIN hosts h" in ENDPOINTS_SQL
    assert "JOIN services s" in ENDPOINTS_SQL
    assert "h.program_id = %s::uuid" in ENDPOINTS_SQL
    assert "FROM services s" in TECHNOLOGIES_SQL
    assert "JOIN ip_addresses ip" in TECHNOLOGIES_SQL
    assert "ip.program_id = %s::uuid" in TECHNOLOGIES_SQL
    assert "raw_artifacts" not in ENDPOINTS_SQL
    assert "raw_artifacts" not in TECHNOLOGIES_SQL


def test_endpoint_document_is_bounded_and_does_not_expose_raw_fields() -> None:
    document = build_endpoint_document(
        {
            "id": "endpoint-1",
            "program_id": "program-1",
            "host_id": "host-1",
            "service_id": "service-1",
            "host": "api.example.com",
            "scheme": "https",
            "port": 443,
            "path": "/" + ("a" * 10_000),
            "normalized_path": "/{id}",
            "methods": ["GET"],
            "status_code": 200,
            "technologies": {"nginx": True},
            "raw_body": "must-not-leak",
        }
    )

    assert document["id"] == "endpoint-1"
    assert document["program_id"] == "program-1"
    assert len(document["path"]) <= 2_048
    assert "must-not-leak" not in str(document)


def test_technology_document_normalizes_names_without_values() -> None:
    document = build_technology_document(
        {
            "service_id": "service-1",
            "program_id": "program-1",
            "address": "192.0.2.10",
            "scheme": "https",
            "port": 443,
            "technologies": {
                "nginx": True,
                "React": {"version": "secret-version-detail"},
                "ignored": False,
            },
        }
    )

    assert document["id"] == "service-1"
    assert document["technology_names"] == ["nginx", "react"]
    assert "secret-version-detail" not in str(document)
