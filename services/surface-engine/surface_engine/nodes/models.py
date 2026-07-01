from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

SURFACE_NODE_FEATURE_VERSION = "surface-node-v1"
SURFACE_SNAPSHOT_ALGORITHM = "surface-map"
SURFACE_SNAPSHOT_ALGORITHM_VERSION = "surface-map-v1"


@dataclass(frozen=True)
class SurfaceNodeDraft:
    """Shape-only node ready to be persisted into surface_nodes.

    Drafts never contain raw request/response bodies, raw header values, query
    values, cookies, authorization material, or legacy body previews. The
    observation row is used only to derive canonical route/request/response
    shape material.
    """

    program_id: str
    node_type: str
    node_fingerprint: str
    feature_fingerprint: str
    feature_version: str
    features_json: dict[str, Any]
    safe_for_search: bool
    ref_type: str | None = None
    ref_id: str | None = None
    host: str | None = None
    path: str | None = None
    route_template: str | None = None
    method: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    first_seen: datetime | str | None = None
    last_seen: datetime | str | None = None


@dataclass(frozen=True)
class SurfaceSnapshotDraft:
    """Snapshot metadata produced before writing surface_nodes."""

    program_id: str
    snapshot_fingerprint: str
    algorithm: str
    algorithm_version: str
    input_watermark: str | None
    source_window_start: datetime | str | None
    source_window_end: datetime | str | None
    stats_json: dict[str, Any]
