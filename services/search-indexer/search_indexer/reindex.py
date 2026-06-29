"""Compatibility exports for search-indexer reindexing.

New code should import mappings from ``reindex_mappings``, operations from
``reindex_ops``, and CLI handlers from ``reindex_cli``. This module remains
small so existing imports and ``python -m search_indexer`` keep working.
"""
from __future__ import annotations

from search_indexer.reindex_cli import build_parser, main
from search_indexer.reindex_mappings import (
    ARTIFACTS_PREVIEW_INDEX,
    DETECTION_SIGNALS_INDEX,
    ENDPOINTS_INDEX,
    FINDINGS_INDEX,
    HTTP_OBSERVATIONS_INDEX,
    HYPOTHESES_INDEX,
    INDEX_MAPPINGS,
    INDEX_RETENTION_POLICIES,
    SURFACE_COMPONENTS_INDEX,
    SURFACE_DELTAS_INDEX,
    TARGETS,
    TECHNOLOGIES_INDEX,
    ReindexFilters,
    TargetSpec,
    delete_after_policy,
    searchable_text,
    single_node_settings,
)
from search_indexer.reindex_ops import (
    build_reindex_filters,
    cleanup_indexes,
    reindex_target,
    run_cleanup,
    run_reindex,
    selected_targets,
)

__all__ = [
    "ARTIFACTS_PREVIEW_INDEX",
    "DETECTION_SIGNALS_INDEX",
    "ENDPOINTS_INDEX",
    "FINDINGS_INDEX",
    "HTTP_OBSERVATIONS_INDEX",
    "HYPOTHESES_INDEX",
    "INDEX_MAPPINGS",
    "INDEX_RETENTION_POLICIES",
    "SURFACE_COMPONENTS_INDEX",
    "SURFACE_DELTAS_INDEX",
    "TARGETS",
    "TECHNOLOGIES_INDEX",
    "ReindexFilters",
    "TargetSpec",
    "build_parser",
    "build_reindex_filters",
    "cleanup_indexes",
    "delete_after_policy",
    "main",
    "reindex_target",
    "run_cleanup",
    "run_reindex",
    "searchable_text",
    "selected_targets",
    "single_node_settings",
]


if __name__ == "__main__":
    raise SystemExit(main())
