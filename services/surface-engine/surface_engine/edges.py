from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .fingerprints import stable_hash
from .nodes import SurfaceNodeDraft

SURFACE_EDGE_ALGORITHM_VERSION = "surface-edge-v1"


@dataclass(frozen=True)
class SurfaceEdgeDraft:
    """Shape-only edge ready to be persisted into surface_edges.

    Edges are derived from deterministic fingerprints already present on
    SurfaceNodeDrafts. They do not classify business meaning such as admin/API;
    they only connect observed endpoint shapes to their route and response-shape
    coordinates so graph algorithms can reason over structure.
    """

    program_id: str
    src_node_fingerprint: str
    dst_node_fingerprint: str
    edge_type: str
    weight: float
    edge_fingerprint: str
    algorithm_version: str
    evidence_json: dict[str, Any]


def build_surface_edges_from_nodes(nodes: Iterable[SurfaceNodeDraft]) -> list[SurfaceEdgeDraft]:
    node_list = list(nodes)
    by_route_fingerprint = _index_by_feature_fingerprint(node_list, node_type="route_template")
    by_response_fingerprint = _index_by_feature_fingerprint(node_list, node_type="response_shape")
    drafts: list[SurfaceEdgeDraft] = []

    for endpoint in sorted(
        (node for node in node_list if node.node_type == "endpoint"),
        key=lambda node: node.node_fingerprint,
    ):
        route_fingerprint = _feature_text(endpoint.features_json, "route_fingerprint")
        response_shape_fingerprint = _feature_text(endpoint.features_json, "response_shape_fingerprint")
        if route_fingerprint:
            route = by_route_fingerprint.get(route_fingerprint)
            if route is not None:
                drafts.append(
                    _edge(
                        src=endpoint,
                        dst=route,
                        edge_type="HAS_ROUTE_SHAPE",
                        evidence={
                            "basis": "shared_route_fingerprint",
                            "route_fingerprint": route_fingerprint,
                        },
                    )
                )
        if response_shape_fingerprint:
            response = by_response_fingerprint.get(response_shape_fingerprint)
            if response is not None:
                drafts.append(
                    _edge(
                        src=endpoint,
                        dst=response,
                        edge_type="HAS_RESPONSE_SHAPE",
                        evidence={
                            "basis": "shared_response_shape_fingerprint",
                            "response_shape_fingerprint": response_shape_fingerprint,
                        },
                    )
                )

    return dedupe_surface_edge_drafts(drafts)


def dedupe_surface_edge_drafts(edges: Iterable[SurfaceEdgeDraft]) -> list[SurfaceEdgeDraft]:
    grouped: dict[str, SurfaceEdgeDraft] = {}
    for edge in edges:
        grouped.setdefault(edge.edge_fingerprint, edge)
    return sorted(grouped.values(), key=lambda edge: (edge.edge_type, edge.edge_fingerprint))


def _edge(*, src: SurfaceNodeDraft, dst: SurfaceNodeDraft, edge_type: str, evidence: dict[str, Any]) -> SurfaceEdgeDraft:
    edge_fingerprint = stable_hash(
        {
            "version": SURFACE_EDGE_ALGORITHM_VERSION,
            "program_id": src.program_id,
            "src_node_fingerprint": src.node_fingerprint,
            "dst_node_fingerprint": dst.node_fingerprint,
            "edge_type": edge_type,
        }
    )
    return SurfaceEdgeDraft(
        program_id=src.program_id,
        src_node_fingerprint=src.node_fingerprint,
        dst_node_fingerprint=dst.node_fingerprint,
        edge_type=edge_type,
        weight=1.0,
        edge_fingerprint=edge_fingerprint,
        algorithm_version=SURFACE_EDGE_ALGORITHM_VERSION,
        evidence_json={
            **evidence,
            "src_node_type": src.node_type,
            "dst_node_type": dst.node_type,
            "src_node_fingerprint": src.node_fingerprint,
            "dst_node_fingerprint": dst.node_fingerprint,
        },
    )


def _index_by_feature_fingerprint(
    nodes: list[SurfaceNodeDraft],
    *,
    node_type: str,
) -> dict[str, SurfaceNodeDraft]:
    indexed: dict[str, SurfaceNodeDraft] = {}
    for node in nodes:
        if node.node_type == node_type:
            indexed.setdefault(node.feature_fingerprint, node)
    return indexed


def _feature_text(features: dict[str, Any], key: str) -> str | None:
    value = features.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
