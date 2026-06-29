from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from .row_codec import optional_int as _optional_int
from .surface_component_materialization_models import (
    SurfaceComponentMaterializationPayload,
    SurfaceComponentMaterializedItem,
)
from .surface_component_report import SurfaceComponentReport

SURFACE_COMPONENT_ANALYSIS_ALGORITHM = "surface-component-report"
SURFACE_COMPONENT_ANALYSIS_VERSION = "surface-component-analysis-v1"


def build_materialization_payload(
    report: SurfaceComponentReport,
    *,
    settings_json: Mapping[str, Any] | None = None,
    algorithm: str = SURFACE_COMPONENT_ANALYSIS_ALGORITHM,
    algorithm_version: str = SURFACE_COMPONENT_ANALYSIS_VERSION,
) -> SurfaceComponentMaterializationPayload:
    if not algorithm.strip():
        raise ValueError("algorithm must not be empty")
    if not algorithm_version.strip():
        raise ValueError("algorithm_version must not be empty")
    settings = dict(settings_json or {})
    report_payload = report.to_dict()
    items = component_items_from_report(report)
    return SurfaceComponentMaterializationPayload(
        run_id=uuid4(),
        program_id=report.program_id,
        snapshot_id=report.snapshot_id,
        previous_snapshot_id=report.previous_snapshot_id,
        algorithm=algorithm,
        algorithm_version=algorithm_version,
        report_fingerprint=_fingerprint(
            {
                "algorithm": algorithm,
                "algorithm_version": algorithm_version,
                "report": report_payload,
                "settings": settings,
            }
        ),
        settings_json=settings,
        stats_json={
            "component_count": len(items),
            "profile_count": len(report.profiles),
            "drift_count": len(report.drift),
            "bridge_count": len(report.bridges),
            "outlier_count": len(report.outliers),
            "coverage_count": len(report.coverage),
            "action_candidate_count": len(report.action_candidates),
            "materialized_at": datetime.now(UTC).isoformat(),
        },
        items=items,
        action_candidate_count=len(report.action_candidates),
    )


def component_items_from_report(report: SurfaceComponentReport) -> tuple[SurfaceComponentMaterializedItem, ...]:
    component_ids = _component_ids(report)
    profiles = {item.component_id: asdict(item) for item in report.profiles}
    drift = {item.current_component_id: asdict(item) for item in report.drift}
    bridges = {item.component_id: asdict(item) for item in report.bridges}
    outliers = {item.component_id: asdict(item) for item in report.outliers}
    coverage = {item.component_id: asdict(item) for item in report.coverage}
    candidates: dict[int, list[dict[str, Any]]] = {}
    for item in report.action_candidates:
        candidates.setdefault(item.component_id, []).append(asdict(item))
    return tuple(
        _component_item(
            component_id,
            profile=profiles.get(component_id, {}),
            drift_item=drift.get(component_id, {}),
            bridge=bridges.get(component_id, {}),
            outlier=outliers.get(component_id, {}),
            coverage_item=coverage.get(component_id, {}),
            candidate_items=candidates.get(component_id, []),
        )
        for component_id in sorted(component_ids)
    )


def _component_ids(report: SurfaceComponentReport) -> set[int]:
    component_ids: set[int] = set()
    for collection in (report.profiles, report.drift, report.bridges, report.outliers, report.coverage, report.action_candidates):
        for item in collection:
            component_ids.add(int(getattr(item, "component_id", getattr(item, "current_component_id", 0))))
    return component_ids


def _component_item(
    component_id: int,
    *,
    profile: Mapping[str, Any],
    drift_item: Mapping[str, Any],
    bridge: Mapping[str, Any],
    outlier: Mapping[str, Any],
    coverage_item: Mapping[str, Any],
    candidate_items: list[dict[str, Any]],
) -> SurfaceComponentMaterializedItem:
    node_count = _first_int(profile, bridge, outlier, coverage_item, drift_item, key="node_count")
    if node_count == 0:
        node_count = int(drift_item.get("current_node_count", 0) or 0)
    return SurfaceComponentMaterializedItem(
        component_id=component_id,
        node_count=node_count,
        changed_node_count=_first_int(profile, bridge, outlier, coverage_item, key="changed_node_count"),
        structural_pressure_score=_optional_int(profile.get("structural_pressure_score")),
        drift_score=_optional_int(drift_item.get("drift_score")),
        bridge_pressure_score=_optional_int(bridge.get("bridge_pressure_score")),
        outlier_score=_optional_int(outlier.get("outlier_score")),
        coverage_score=_optional_int(coverage_item.get("coverage_score")),
        exploration_priority_score=_optional_int(coverage_item.get("exploration_priority_score")),
        action_candidate_count=len(candidate_items),
        metrics_json={
            "profile": profile or None,
            "drift": drift_item or None,
            "bridge": bridge or None,
            "outlier": outlier or None,
            "coverage": coverage_item or None,
        },
        action_candidates_json=candidate_items,
    )


def _first_int(*items: Mapping[str, Any], key: str) -> int:
    for item in items:
        value = item.get(key)
        if value is not None:
            return int(value)
    return 0


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
