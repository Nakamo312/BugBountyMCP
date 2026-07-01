from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from surface_engine.fingerprints import build_snapshot_fingerprint

from .models import SURFACE_SNAPSHOT_ALGORITHM, SURFACE_SNAPSHOT_ALGORITHM_VERSION, SurfaceNodeDraft, SurfaceSnapshotDraft


def build_snapshot_draft(
    *,
    program_id: str,
    nodes: Iterable[SurfaceNodeDraft],
    source_rows: Iterable[Mapping[str, Any]],
    algorithm_version: str = SURFACE_SNAPSHOT_ALGORITHM_VERSION,
) -> SurfaceSnapshotDraft:
    """Build deterministic snapshot metadata from input rows and deduped nodes."""

    node_list = list(nodes)
    rows = list(source_rows)
    observed_values = [row.get("observed_at") for row in rows if row.get("observed_at") is not None]
    source_window_start = min(observed_values) if observed_values else None
    source_window_end = max(observed_values) if observed_values else None
    input_ids = sorted(str(row.get("id")) for row in rows if row.get("id") is not None)
    input_watermark = input_ids[-1] if input_ids else None
    snapshot_fingerprint = build_snapshot_fingerprint(
        program_id=program_id,
        algorithm_version=algorithm_version,
        node_fingerprints=[node.node_fingerprint for node in node_list],
        input_ids=input_ids,
    )
    node_type_counts = Counter(node.node_type for node in node_list)
    stats_json: dict[str, Any] = {
        "source": "http_observations",
        "observations_read": len(rows),
        "nodes_deduped": len(node_list),
        "node_types": dict(sorted(node_type_counts.items())),
    }
    return SurfaceSnapshotDraft(
        program_id=program_id,
        snapshot_fingerprint=snapshot_fingerprint,
        algorithm=SURFACE_SNAPSHOT_ALGORITHM,
        algorithm_version=algorithm_version,
        input_watermark=input_watermark,
        source_window_start=source_window_start,
        source_window_end=source_window_end,
        stats_json=stats_json,
    )
