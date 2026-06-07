"""Backfill normalized PostgreSQL data into OpenSearch indexes."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from search_indexer.documents import (
    build_artifact_preview_document,
    build_detection_signal_document,
    build_finding_document,
    build_http_observation_document,
)
from search_indexer.opensearch_client import OpenSearchClient
from search_indexer.postgres_reader import PostgresSearchReader, batched_offsets
from search_indexer.settings import Settings, load_settings

HTTP_OBSERVATIONS_INDEX = "bb-http-observations"
ARTIFACTS_PREVIEW_INDEX = "bb-artifacts-preview"
FINDINGS_INDEX = "bb-findings"
DETECTION_SIGNALS_INDEX = "bb-detection-signals"


def single_node_settings() -> dict[str, Any]:
    return {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }


def searchable_text(*, keyword_ignore_above: int = 1024) -> dict[str, Any]:
    return {
        "type": "text",
        "fields": {
            "keyword": {
                "type": "keyword",
                "ignore_above": keyword_ignore_above,
            }
        },
    }


def delete_after_policy(*, description: str, delete_after: str) -> dict[str, Any]:
    return {
        "policy": {
            "description": description,
            "default_state": "open",
            "states": [
                {
                    "name": "open",
                    "actions": [],
                    "transitions": [
                        {
                            "state_name": "delete",
                            "conditions": {"min_index_age": delete_after},
                        }
                    ],
                },
                {
                    "name": "delete",
                    "actions": [{"delete": {}}],
                    "transitions": [],
                },
            ],
        }
    }


INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    HTTP_OBSERVATIONS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "observed_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "correlation_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "service_id": {"type": "keyword"},
                "raw_artifact_id": {"type": "keyword"},
                "body_artifact_id": {"type": "keyword"},
                "method": {"type": "keyword"},
                "scheme": {"type": "keyword"},
                "host": {"type": "keyword"},
                "url": searchable_text(keyword_ignore_above=4096),
                "port": {"type": "integer"},
                "path": searchable_text(keyword_ignore_above=2048),
                "status_code": {"type": "integer"},
                "content_type": {"type": "keyword"},
                "title": searchable_text(),
                "headers": {"type": "flat_object"},
                "body_sha256": {"type": "keyword"},
                "body_size_bytes": {"type": "long"},
                "body_preview": {"type": "text"},
                "source_tool": {"type": "keyword"},
                "metadata": {"type": "flat_object"},
            },
        },
    },
    ARTIFACTS_PREVIEW_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "node_id": {"type": "keyword"},
                "event_name": {"type": "keyword"},
                "artifact_type": {"type": "keyword"},
                "sha256": {"type": "keyword"},
                "storage_uri": {"type": "keyword"},
                "size_bytes": {"type": "long"},
                "metadata": {"type": "flat_object"},
                "preview": {"type": "text"},
            },
        },
    },
    FINDINGS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "vuln_type_id": {"type": "keyword"},
                "host_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "parameter_id": {"type": "keyword"},
                "payload_id": {"type": "keyword"},
                "execution_id": {"type": "keyword"},
                "vuln_code": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "category": {"type": "keyword"},
                "description": searchable_text(),
                "evidence": {"type": "flat_object"},
                "verified": {"type": "boolean"},
                "false_positive": {"type": "boolean"},
            },
        },
    },
    DETECTION_SIGNALS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "event_store_id": {"type": "keyword"},
                "event_id": {"type": "keyword"},
                "event_type": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "correlation_id": {"type": "keyword"},
                "causation_id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "profile": {"type": "keyword"},
                "confidence": {"type": "float"},
            },
        },
    },
}

INDEX_RETENTION_POLICIES: dict[str, dict[str, Any]] = {
    ARTIFACTS_PREVIEW_INDEX: {
        "policy_id": "bb-artifacts-preview-dev-retention",
        "delete_after": "7d",
        "policy": delete_after_policy(
            description="Delete rebuildable artifact preview indexes after 7 days in dev.",
            delete_after="7d",
        ),
    },
    HTTP_OBSERVATIONS_INDEX: {
        "policy_id": "bb-http-observations-dev-retention",
        "delete_after": "30d",
        "policy": delete_after_policy(
            description="Delete rebuildable HTTP observation indexes after 30 days in dev.",
            delete_after="30d",
        ),
    },
    DETECTION_SIGNALS_INDEX: {
        "policy_id": "bb-detection-signals-dev-retention",
        "delete_after": "90d",
        "policy": delete_after_policy(
            description="Delete rebuildable detection signal indexes after 90 days in dev.",
            delete_after="90d",
        ),
    },
}


TargetSpec = tuple[
    str,
    Callable[[PostgresSearchReader, int, int], list[dict[str, Any]]],
    Callable[[Mapping[str, Any]], dict[str, Any]],
]


TARGETS: dict[str, TargetSpec] = {
    "http-observations": (
        HTTP_OBSERVATIONS_INDEX,
        lambda reader, limit, offset: reader.fetch_http_observations(limit=limit, offset=offset),
        build_http_observation_document,
    ),
    "artifacts": (
        ARTIFACTS_PREVIEW_INDEX,
        lambda reader, limit, offset: reader.fetch_artifacts(limit=limit, offset=offset),
        build_artifact_preview_document,
    ),
    "findings": (
        FINDINGS_INDEX,
        lambda reader, limit, offset: reader.fetch_findings(limit=limit, offset=offset),
        build_finding_document,
    ),
    "detection-signals": (
        DETECTION_SIGNALS_INDEX,
        lambda reader, limit, offset: reader.fetch_detection_signals(limit=limit, offset=offset),
        build_detection_signal_document,
    ),
}


def reindex_target(
    *,
    target: str,
    reader: PostgresSearchReader,
    client: OpenSearchClient,
    limit: int,
    batch_size: int,
) -> int:
    index_name, fetch_rows, build_document = TARGETS[target]
    retention = INDEX_RETENTION_POLICIES.get(index_name)
    if retention:
        client.ensure_ism_policy(retention["policy_id"], retention["policy"])
    client.ensure_index(index_name, INDEX_MAPPINGS[index_name])
    if retention:
        client.apply_ism_policy(index_name, retention["policy_id"])
    indexed = 0
    for current_limit, offset in batched_offsets(limit=limit, batch_size=batch_size):
        rows = fetch_rows(reader, current_limit, offset)
        if not rows:
            break
        documents = [build_document(row) for row in rows]
        client.bulk_index(index_name, documents)
        indexed += len(documents)
        if len(rows) < current_limit:
            break
    return indexed


def selected_targets(target: str) -> Iterable[str]:
    if target == "all":
        return TARGETS.keys()
    return [target]


def cleanup_indexes(*, client: OpenSearchClient, target: str) -> list[str]:
    deleted = []
    for name in selected_targets(target):
        index_name = TARGETS[name][0]
        client.delete_index(index_name)
        deleted.append(index_name)
    return deleted


def run_reindex(
    *,
    settings: Settings,
    target: str,
    limit: int,
    batch_size: int,
) -> dict[str, int]:
    reader = PostgresSearchReader(settings.postgres_dsn)
    client = OpenSearchClient(
        settings.opensearch_url,
        timeout_seconds=settings.opensearch_timeout_seconds,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        verify_certs=settings.opensearch_verify_certs,
    )
    return {
        name: reindex_target(
            target=name,
            reader=reader,
            client=client,
            limit=limit,
            batch_size=batch_size,
        )
        for name in selected_targets(target)
    }


def run_cleanup(*, settings: Settings, target: str) -> list[str]:
    client = OpenSearchClient(
        settings.opensearch_url,
        timeout_seconds=settings.opensearch_timeout_seconds,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        verify_certs=settings.opensearch_verify_certs,
    )
    return cleanup_indexes(client=client, target=target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="search_indexer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    reindex_parser = subparsers.add_parser("reindex")
    reindex_parser.add_argument(
        "--target",
        choices=["all", *TARGETS.keys()],
        default="all",
    )
    reindex_parser.add_argument("--limit", type=int, default=1000)
    reindex_parser.add_argument("--batch-size", type=int, default=500)

    cleanup_parser = subparsers.add_parser("cleanup-indexes")
    cleanup_parser.add_argument(
        "--target",
        choices=["all", *TARGETS.keys()],
        default="all",
    )
    cleanup_parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for deleting rebuildable OpenSearch indexes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "reindex":
        results = run_reindex(
            settings=load_settings(),
            target=args.target,
            limit=args.limit,
            batch_size=args.batch_size,
        )
        for name, count in results.items():
            print(f"{name}: indexed {count}")
        return 0
    if args.command == "cleanup-indexes":
        if not args.yes:
            parser.error("cleanup-indexes requires --yes")
        deleted = run_cleanup(settings=load_settings(), target=args.target)
        for index_name in deleted:
            print(f"deleted index: {index_name}")
        return 0
    parser.error(f"Unsupported command: {args.command}")
    return 2
