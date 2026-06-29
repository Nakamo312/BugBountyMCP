from __future__ import annotations

from typing import Any, Mapping

from ..contracts import GraphFactBatch
from .surface_map_fact_builder import build_surface_map_graph_fact_batch
from .surface_map_keys import surface_delta_key, surface_map_dedupe_key, surface_node_key


class SurfaceMapGraphFactProducer:
    """Project Surface Map snapshots/nodes/edges/deltas into Neo4j.

    This producer keeps the graph mathematical: SurfaceNode identities are
    snapshot-local shape vertices and SURFACE_EDGE relationships carry the
    deterministic edge_type/weight from surface_edges. It does not emit
    vulnerability labels or hand-written semantic classes.
    """

    def __init__(self, *, parser_version: str = "surface-map.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        return build_surface_map_graph_fact_batch(rows, parser_version=self._parser_version)


__all__ = [
    "SurfaceMapGraphFactProducer",
    "surface_delta_key",
    "surface_map_dedupe_key",
    "surface_node_key",
]
