from __future__ import annotations

from typing import Mapping, Any
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .surface_map_keys import surface_delta_key, surface_node_key
from .surface_map_projection import SurfaceMapProjection, surface_map_projection_from_row

SurfaceFact = GraphNodeFact | GraphEdgeFact


def build_surface_map_graph_fact_batch(rows: list[Mapping[str, Any]], *, parser_version: str) -> GraphFactBatch | None:
    facts: list[SurfaceFact] = []
    seen: set[str] = set()
    batch_program_id: UUID | None = None

    for projection in map(surface_map_projection_from_row, rows):
        batch_program_id = _batch_program_id(batch_program_id, projection.program_id)
        for fact in _surface_map_facts(projection):
            _append_once(facts, seen, fact)

    if batch_program_id is None or not facts:
        return None
    return GraphFactBatch(
        program_id=batch_program_id,
        facts=facts,
        produced_by="surface-map",
        parser_version=parser_version,
    )


def _batch_program_id(current: UUID | None, next_program_id: UUID) -> UUID:
    if current is None:
        return next_program_id
    if current != next_program_id:
        raise ValueError("surface map batch cannot mix program_id values")
    return current


def _surface_map_facts(projection: SurfaceMapProjection) -> list[SurfaceFact]:
    if projection.snapshot_id is None:
        return []
    lineage = _lineage(projection)
    return [
        *_snapshot_facts(projection, lineage=lineage),
        *_surface_node_facts(projection, lineage=lineage),
        *_surface_edge_facts(projection, lineage=lineage),
        *_surface_delta_facts(projection, lineage=lineage),
    ]


def _snapshot_facts(projection: SurfaceMapProjection, *, lineage: dict[str, object]) -> list[SurfaceFact]:
    return [
        GraphNodeFact(
            **lineage,
            kind="SurfaceSnapshot",
            key=projection.snapshot_id or "",
            properties={
                "snapshot_id": projection.snapshot_id,
                "snapshot_fingerprint": projection.snapshot_fingerprint,
                "algorithm_version": projection.snapshot_algorithm_version,
                "input_watermark": projection.input_watermark,
            },
        )
    ]


def _surface_node_facts(projection: SurfaceMapProjection, *, lineage: dict[str, object]) -> list[SurfaceFact]:
    if projection.snapshot_id is None or projection.node_fingerprint is None:
        return []
    node_key = surface_node_key(snapshot_id=projection.snapshot_id, node_fingerprint=projection.node_fingerprint)
    return [
        _surface_node(projection, lineage=lineage, node_key=node_key),
        _surface_fingerprint(projection, lineage=lineage),
        GraphEdgeFact(
            **lineage,
            src_kind="SurfaceSnapshot",
            src_key=projection.snapshot_id,
            edge_kind="HAS_SURFACE_NODE",
            dst_kind="SurfaceNode",
            dst_key=node_key,
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="SurfaceNode",
            src_key=node_key,
            edge_kind="HAS_SURFACE_FINGERPRINT",
            dst_kind="SurfaceFingerprint",
            dst_key=projection.node_fingerprint,
        ),
        *_surface_representation_edges(projection, lineage=lineage, node_key=node_key),
    ]


def _surface_node(
    projection: SurfaceMapProjection,
    *,
    lineage: dict[str, object],
    node_key: str,
) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="SurfaceNode",
        key=node_key,
        properties={
            "snapshot_id": projection.snapshot_id,
            "node_fingerprint": projection.node_fingerprint,
            "node_type": projection.node_type,
            "feature_fingerprint": projection.feature_fingerprint,
            "ref_type": projection.ref_type,
            "ref_id": projection.ref_id,
            "host": projection.host,
            "path": projection.path,
            "route_template": projection.route_template,
            "method": projection.method,
            "status_code": projection.status_code,
            "content_type": projection.content_type,
            "canonical_entity_key": _surface_canonical_entity_key(projection),
        },
    )


def _surface_representation_edges(
    projection: SurfaceMapProjection,
    *,
    lineage: dict[str, object],
    node_key: str,
) -> list[SurfaceFact]:
    if not projection.host:
        return []
    # Exact bridge available with the current surface schema: a surface node observed
    # on a host can point to the canonical Host node. Endpoint/request bridges need
    # service_key; do not fake them from route text alone.
    return [
        GraphNodeFact(
            **lineage,
            kind="Host",
            key=projection.host,
            properties={"hostname": projection.host, "display_label": projection.host},
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="SurfaceNode",
            src_key=node_key,
            edge_kind="REPRESENTS",
            dst_kind="Host",
            dst_key=projection.host,
            properties={"bridge_type": "surface_host"},
        ),
    ]


def _surface_canonical_entity_key(projection: SurfaceMapProjection) -> str | None:
    if projection.host and projection.method and (projection.route_template or projection.path):
        route = projection.route_template or projection.path
        return f"surface:{projection.host}:{projection.method}:{route}"
    if projection.host:
        return f"host:{projection.host}"
    return None


def _surface_fingerprint(projection: SurfaceMapProjection, *, lineage: dict[str, object]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="SurfaceFingerprint",
        key=projection.node_fingerprint or "",
        properties={"fingerprint": projection.node_fingerprint, "fingerprint_type": "surface_node"},
    )


def _surface_edge_facts(projection: SurfaceMapProjection, *, lineage: dict[str, object]) -> list[SurfaceFact]:
    if not (projection.snapshot_id and projection.src_node_fingerprint and projection.dst_node_fingerprint):
        return []
    return [
        GraphEdgeFact(
            **lineage,
            src_kind="SurfaceNode",
            src_key=surface_node_key(snapshot_id=projection.snapshot_id, node_fingerprint=projection.src_node_fingerprint),
            edge_kind="SURFACE_EDGE",
            dst_kind="SurfaceNode",
            dst_key=surface_node_key(snapshot_id=projection.snapshot_id, node_fingerprint=projection.dst_node_fingerprint),
            properties={
                "edge_type": projection.edge_type,
                "edge_fingerprint": projection.edge_fingerprint,
                "weight": projection.edge_weight,
                "algorithm_version": projection.edge_algorithm_version,
            },
        )
    ]


def _surface_delta_facts(projection: SurfaceMapProjection, *, lineage: dict[str, object]) -> list[SurfaceFact]:
    if not (projection.snapshot_id and projection.delta_subject_fingerprint and projection.delta_type):
        return []
    delta_key = surface_delta_key(
        snapshot_id=projection.snapshot_id,
        delta_type=projection.delta_type,
        subject_fingerprint=projection.delta_subject_fingerprint,
    )
    return [
        GraphNodeFact(
            **lineage,
            kind="SurfaceDelta",
            key=delta_key,
            properties={
                "snapshot_id": projection.snapshot_id,
                "from_snapshot_id": projection.from_snapshot_id,
                "delta_type": projection.delta_type,
                "subject_type": projection.delta_subject_type,
                "subject_fingerprint": projection.delta_subject_fingerprint,
                "novelty_score": projection.novelty_score,
            },
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="SurfaceSnapshot",
            src_key=projection.snapshot_id,
            edge_kind="HAS_SURFACE_DELTA",
            dst_kind="SurfaceDelta",
            dst_key=delta_key,
        ),
    ]


def _lineage(projection: SurfaceMapProjection) -> dict[str, object]:
    return {"program_id": projection.program_id, "producer": "surface-map", "confidence": 1.0}


def _append_once(facts: list[SurfaceFact], seen: set[str], fact: SurfaceFact) -> None:
    if fact.identity_key in seen:
        return
    seen.add(fact.identity_key)
    facts.append(fact)
