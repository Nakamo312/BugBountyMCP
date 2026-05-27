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

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    HTTP_OBSERVATIONS_INDEX: {
        "mappings": {
            "dynamic": True,
            "properties": {
                "@timestamp": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "correlation_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "service_id": {"type": "keyword"},
                "host": {"type": "keyword"},
                "url": {"type": "keyword"},
                "path": {"type": "keyword"},
                "status_code": {"type": "integer"},
                "body_preview": {"type": "text"},
                "title": {"type": "text"},
            },
        },
    },
    ARTIFACTS_PREVIEW_INDEX: {
        "mappings": {
            "dynamic": True,
            "properties": {
                "@timestamp": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "artifact_type": {"type": "keyword"},
                "sha256": {"type": "keyword"},
                "storage_uri": {"type": "keyword"},
            },
        },
    },
    FINDINGS_INDEX: {
        "mappings": {
            "dynamic": True,
            "properties": {
                "program_id": {"type": "keyword"},
                "host_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "vuln_code": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "description": {"type": "text"},
            },
        },
    },
    DETECTION_SIGNALS_INDEX: {
        "mappings": {
            "dynamic": False,
            "properties": {
                "@timestamp": {"type": "date"},
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
    client.ensure_index(index_name, INDEX_MAPPINGS[index_name])
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
    parser.error(f"Unsupported command: {args.command}")
    return 2
