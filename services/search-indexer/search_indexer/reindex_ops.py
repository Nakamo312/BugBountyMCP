"""OpenSearch reindex and cleanup operations."""
from __future__ import annotations

from collections.abc import Iterable

from search_indexer.opensearch_client import OpenSearchClient
from search_indexer.postgres_reader import PostgresSearchReader, batched_offsets
from search_indexer.projection_state import ProjectionStateStore
from search_indexer.settings import Settings
from search_indexer.target_contracts import normalize_target_filters, validate_search_target
from search_indexer.reindex_mappings import (
    INDEX_MAPPINGS,
    INDEX_RETENTION_POLICIES,
    TARGETS,
    ReindexFilters,
)


def reindex_target(
    *,
    target: str,
    reader: PostgresSearchReader,
    client: OpenSearchClient,
    limit: int,
    batch_size: int,
    program_id: str | None = None,
    projection_state_store: ProjectionStateStore | None = None,
    filters: ReindexFilters | None = None,
) -> int:
    target = validate_search_target(target)
    filters = normalize_target_filters(target=target, filters=filters or {})
    spec = TARGETS[target]
    retention = INDEX_RETENTION_POLICIES.get(spec.index_name)
    if retention:
        client.ensure_ism_policy(retention["policy_id"], retention["policy"])
    client.ensure_index(spec.index_name, INDEX_MAPPINGS[spec.index_name])
    if retention:
        client.apply_ism_policy(spec.index_name, retention["policy_id"])
    projection_run = None
    if program_id is not None and projection_state_store is not None:
        projection_run = projection_state_store.start(
            program_id=program_id,
            projection_name=target,
            total_count=reader.count_target(target=target, program_id=program_id, filters=dict(filters)),
        )
    indexed = 0
    try:
        for current_limit, offset in batched_offsets(limit=limit, batch_size=batch_size):
            rows = spec.fetch_rows(reader, current_limit, offset, program_id, filters)
            if not rows:
                break
            documents = [spec.build_document(row) for row in rows]
            client.bulk_index(spec.index_name, documents)
            indexed += len(documents)
            if len(rows) < current_limit:
                break
    except Exception as exc:
        if projection_run is not None:
            projection_state_store.fail(projection_run, error=str(exc))
        raise
    if projection_run is not None:
        projection_state_store.complete(projection_run, indexed_count=indexed)
    return indexed


def selected_targets(target: str) -> Iterable[str]:
    target = validate_search_target(target, allow_all=True)
    if target == "all":
        return TARGETS.keys()
    return [target]


def cleanup_indexes(*, client: OpenSearchClient, target: str) -> list[str]:
    deleted = []
    for name in selected_targets(target):
        index_name = TARGETS[name].index_name
        client.delete_index(index_name)
        deleted.append(index_name)
    return deleted


def run_reindex(
    *,
    settings: Settings,
    target: str,
    limit: int,
    batch_size: int,
    program_id: str | None = None,
    filters: ReindexFilters | None = None,
) -> dict[str, int]:
    reader = PostgresSearchReader(settings.postgres_dsn)
    client = OpenSearchClient(
        settings.opensearch_url,
        timeout_seconds=settings.opensearch_timeout_seconds,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        verify_certs=settings.opensearch_verify_certs,
    )
    projection_state_store = ProjectionStateStore(settings.postgres_dsn) if program_id else None
    return {
        name: reindex_target(
            target=name,
            reader=reader,
            client=client,
            limit=limit,
            batch_size=batch_size,
            program_id=program_id,
            projection_state_store=projection_state_store,
            filters=filters,
        )
        for name in selected_targets(target)
    }


def build_reindex_filters(*, target: str, analysis_run_id: str | None, snapshot_id: str | None) -> dict[str, str]:
    target = validate_search_target(target, allow_all=True)
    filters: dict[str, str] = {}
    if analysis_run_id:
        if target != "surface-components":
            raise ValueError("--analysis-run-id is only supported with --target surface-components")
        filters["analysis_run_id"] = analysis_run_id
    if snapshot_id:
        if target not in {"surface-components", "surface-deltas"}:
            raise ValueError("--snapshot-id is only supported with --target surface-components or surface-deltas")
        filters["snapshot_id"] = snapshot_id
    return normalize_target_filters(target="surface-components" if target == "all" else target, filters=filters) if filters else {}


def run_cleanup(*, settings: Settings, target: str) -> list[str]:
    client = OpenSearchClient(
        settings.opensearch_url,
        timeout_seconds=settings.opensearch_timeout_seconds,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
        verify_certs=settings.opensearch_verify_certs,
    )
    return cleanup_indexes(client=client, target=target)


def connect_postgres(dsn: str):
    from search_indexer.events import _load_psycopg2

    psycopg2, _Json, _RealDictCursor = _load_psycopg2()
    return psycopg2.connect(dsn)


# Backward-compatible alias for older imports; new modules use connect_postgres.
_connect_postgres = connect_postgres
