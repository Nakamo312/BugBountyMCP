from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .edges import SurfaceEdgeDraft
from .nodes import SurfaceNodeDraft


@dataclass(frozen=True)
class SurfaceDeltaDraft:
    """One structural delta between two surface snapshots.

    The score is intentionally graph-shape oriented. It rewards structural role
    change such as new degree/attachment, not vulnerability labels or domain
    word lists.
    """

    program_id: str
    from_snapshot_id: str | None
    to_snapshot_id: str
    delta_type: str
    subject_type: str
    subject_fingerprint: str
    novelty_score: int
    details_json: dict[str, Any]


def build_surface_deltas(
    *,
    program_id: str,
    from_snapshot_id: str | None,
    to_snapshot_id: str,
    previous_nodes: Iterable[Mapping[str, Any]],
    previous_edges: Iterable[Mapping[str, Any]],
    current_nodes: Iterable[SurfaceNodeDraft],
    current_edges: Iterable[SurfaceEdgeDraft],
) -> list[SurfaceDeltaDraft]:
    previous_node_map = _map_by(previous_nodes, "node_fingerprint")
    previous_edge_map = _map_by(previous_edges, "edge_fingerprint")
    current_node_map = {node.node_fingerprint: node for node in current_nodes}
    current_edge_map = {edge.edge_fingerprint: edge for edge in current_edges}

    current_degree = _degree_by_node(current_edges)
    previous_feature_fingerprints = {
        _optional_text(row.get("feature_fingerprint"))
        for row in previous_nodes
        if _optional_text(row.get("feature_fingerprint")) is not None
    }

    deltas: list[SurfaceDeltaDraft] = []
    for fingerprint, node in sorted(current_node_map.items()):
        if fingerprint in previous_node_map:
            continue
        degree = current_degree.get(fingerprint, 0)
        feature_seen_before = node.feature_fingerprint in previous_feature_fingerprints
        novelty_score = _node_novelty_score(degree=degree, feature_seen_before=feature_seen_before)
        deltas.append(
            SurfaceDeltaDraft(
                program_id=program_id,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                delta_type="node_introduced",
                subject_type=node.node_type,
                subject_fingerprint=fingerprint,
                novelty_score=novelty_score,
                details_json={
                    "node_type": node.node_type,
                    "node_fingerprint": fingerprint,
                    "feature_fingerprint": node.feature_fingerprint,
                    "degree_in_to_snapshot": degree,
                    "feature_seen_before": feature_seen_before,
                    "score_basis": "degree_and_feature_reuse",
                },
            )
        )

    for fingerprint, edge in sorted(current_edge_map.items()):
        if fingerprint in previous_edge_map:
            continue
        src_new = edge.src_node_fingerprint not in previous_node_map
        dst_new = edge.dst_node_fingerprint not in previous_node_map
        novelty_score = _edge_novelty_score(src_new=src_new, dst_new=dst_new)
        deltas.append(
            SurfaceDeltaDraft(
                program_id=program_id,
                from_snapshot_id=from_snapshot_id,
                to_snapshot_id=to_snapshot_id,
                delta_type="edge_introduced",
                subject_type=edge.edge_type,
                subject_fingerprint=fingerprint,
                novelty_score=novelty_score,
                details_json={
                    "edge_type": edge.edge_type,
                    "edge_fingerprint": fingerprint,
                    "src_node_fingerprint": edge.src_node_fingerprint,
                    "dst_node_fingerprint": edge.dst_node_fingerprint,
                    "src_node_introduced": src_new,
                    "dst_node_introduced": dst_new,
                    "score_basis": "endpoint_attachment_change",
                },
            )
        )

    return deltas


def _node_novelty_score(*, degree: int, feature_seen_before: bool) -> int:
    score = 35 + min(max(degree, 0), 5) * 10
    if feature_seen_before:
        score -= 15
    return _bounded_score(score)


def _edge_novelty_score(*, src_new: bool, dst_new: bool) -> int:
    score = 30
    if src_new:
        score += 15
    if dst_new:
        score += 15
    return _bounded_score(score)


def _bounded_score(score: int) -> int:
    return max(0, min(100, int(score)))


def _degree_by_node(edges: Iterable[SurfaceEdgeDraft]) -> dict[str, int]:
    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge.src_node_fingerprint] = degree.get(edge.src_node_fingerprint, 0) + 1
        degree[edge.dst_node_fingerprint] = degree.get(edge.dst_node_fingerprint, 0) + 1
    return degree


def _map_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    mapped: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = _optional_text(row.get(key))
        if value is not None:
            mapped.setdefault(value, row)
    return mapped


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
