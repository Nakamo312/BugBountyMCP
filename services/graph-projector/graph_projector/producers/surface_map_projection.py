from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import optional_int, optional_text, required_row_uuid


@dataclass(frozen=True)
class SurfaceMapProjection:
    program_id: UUID
    snapshot_id: str | None
    snapshot_fingerprint: str | None
    snapshot_algorithm_version: str | None
    input_watermark: str | None
    node_fingerprint: str | None
    node_type: str | None
    ref_type: str | None
    ref_id: str | None
    feature_fingerprint: str | None
    host: str | None
    path: str | None
    route_template: str | None
    method: str | None
    status_code: int | None
    content_type: str | None
    src_node_fingerprint: str | None
    dst_node_fingerprint: str | None
    edge_type: str | None
    edge_fingerprint: str | None
    edge_weight: float
    edge_algorithm_version: str | None
    from_snapshot_id: str | None
    delta_type: str | None
    delta_subject_type: str | None
    delta_subject_fingerprint: str | None
    novelty_score: int


def surface_map_projection_from_row(row: Mapping[str, Any]) -> SurfaceMapProjection:
    return SurfaceMapProjection(
        program_id=required_row_uuid(row, "program_id", context="surface map row"),
        snapshot_id=optional_text(row.get("snapshot_id")),
        snapshot_fingerprint=optional_text(row.get("snapshot_fingerprint")),
        snapshot_algorithm_version=optional_text(row.get("snapshot_algorithm_version")),
        input_watermark=optional_text(row.get("input_watermark")),
        node_fingerprint=optional_text(row.get("node_fingerprint")),
        node_type=optional_text(row.get("node_type")),
        ref_type=optional_text(row.get("ref_type")),
        ref_id=optional_text(row.get("ref_id")),
        feature_fingerprint=optional_text(row.get("feature_fingerprint")),
        host=optional_text(row.get("host")),
        path=optional_text(row.get("path")),
        route_template=optional_text(row.get("route_template")),
        method=optional_text(row.get("method")),
        status_code=optional_int(row.get("status_code")),
        content_type=optional_text(row.get("content_type")),
        src_node_fingerprint=optional_text(row.get("src_node_fingerprint")),
        dst_node_fingerprint=optional_text(row.get("dst_node_fingerprint")),
        edge_type=optional_text(row.get("edge_type")),
        edge_fingerprint=optional_text(row.get("edge_fingerprint")),
        edge_weight=optional_float(row.get("weight")) or 1.0,
        edge_algorithm_version=optional_text(row.get("edge_algorithm_version")),
        from_snapshot_id=optional_text(row.get("from_snapshot_id")),
        delta_type=optional_text(row.get("delta_type")),
        delta_subject_type=optional_text(row.get("delta_subject_type")),
        delta_subject_fingerprint=optional_text(row.get("delta_subject_fingerprint")),
        novelty_score=optional_int(row.get("novelty_score")) or 0,
    )


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
