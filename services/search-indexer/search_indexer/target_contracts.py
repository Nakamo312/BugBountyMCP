"""Bounded target/filter contracts for the OpenSearch projection layer."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SEARCH_INDEX_TARGETS: tuple[str, ...] = (
    "http-observations",
    "artifacts",
    "endpoints",
    "technologies",
    "findings",
    "detection-signals",
    "hypotheses",
    "surface-components",
    "surface-deltas",
)

SURFACE_PROJECTION_TARGETS: frozenset[str] = frozenset({"surface-components", "surface-deltas"})

SEARCH_EVENT_SOURCE_BY_TARGET: dict[str, str] = {
    "surface-components": "surface_component_analysis_run",
    "surface-deltas": "surface_snapshot",
}

TARGET_FILTER_KEYS: dict[str, frozenset[str]] = {
    **{target: frozenset() for target in SEARCH_INDEX_TARGETS},
    "surface-components": frozenset({"analysis_run_id", "snapshot_id"}),
    "surface-deltas": frozenset({"snapshot_id"}),
}


def validate_search_target(target: str, *, allow_all: bool = False) -> str:
    normalized = str(target).strip()
    allowed = set(SEARCH_INDEX_TARGETS)
    if allow_all:
        allowed.add("all")
    if normalized not in allowed:
        raise ValueError(f"unsupported search-indexer target: {normalized}")
    return normalized


def validate_optional_search_target(target: str | None) -> str | None:
    if target is None:
        return None
    return validate_search_target(target)


def validate_surface_projection_target(target: str | None) -> str | None:
    if target is None:
        return None
    normalized = validate_search_target(target)
    if normalized not in SURFACE_PROJECTION_TARGETS:
        raise ValueError(f"unsupported surface projection event target: {normalized}")
    return normalized


def normalize_target_filters(*, target: str, filters: Mapping[str, Any] | None) -> dict[str, str]:
    normalized_target = validate_search_target(target)
    allowed = TARGET_FILTER_KEYS[normalized_target]
    if not filters:
        return {}
    invalid = sorted(set(filters) - allowed)
    if invalid:
        raise ValueError(f"unsupported filter(s) for {normalized_target}: {', '.join(invalid)}")
    normalized: dict[str, str] = {}
    for key, value in filters.items():
        if value is None:
            continue
        stripped = str(value).strip()
        if stripped:
            normalized[key] = stripped
    return normalized


def validate_search_projection_event_contract(*, target: str, source_type: str) -> tuple[str, str]:
    normalized_target = validate_surface_projection_target(target)
    normalized_source_type = str(source_type).strip()
    if not normalized_source_type:
        raise ValueError("source_type must not be empty")
    expected_source_type = SEARCH_EVENT_SOURCE_BY_TARGET[normalized_target]
    if normalized_source_type != expected_source_type:
        raise ValueError(
            f"unsupported source_type for {normalized_target}: {normalized_source_type}; "
            f"expected {expected_source_type}"
        )
    return normalized_target, normalized_source_type
