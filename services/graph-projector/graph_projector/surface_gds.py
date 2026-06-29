from __future__ import annotations

from .surface_gds_models import (
    Neo4jSession,
    SurfaceComponent,
    SurfaceComponentActionCandidate,
    SurfaceComponentBridgeProfile,
    SurfaceComponentCoverageProfile,
    SurfaceComponentDrift,
    SurfaceComponentOutlierProfile,
    SurfaceComponentProfile,
)
from .surface_gds_queries import (
    SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER,
    SURFACE_COMPONENT_BRIDGE_CYPHER,
    SURFACE_COMPONENT_COVERAGE_CYPHER,
    SURFACE_COMPONENT_DRIFT_CYPHER,
    SURFACE_COMPONENT_OUTLIER_CYPHER,
    SURFACE_COMPONENT_PROFILE_CYPHER,
    SURFACE_WCC_CYPHER,
)
from .surface_gds_rows import (
    _component_action_candidate_from_row,
    _component_bridge_from_row,
    _component_coverage_from_row,
    _component_drift_from_row,
    _component_from_row,
    _component_outlier_from_row,
    _component_profile_from_row,
)
from .surface_gds_safety import _safe_graph_name, _safe_probe_id, _unique_graph_name


class SurfaceGraphMathReader:
    """Run GDS over snapshot-local SurfaceNode graphs.

    GDS receives only SurfaceNode vertices and SURFACE_EDGE relationships for
    one snapshot. The first layer returns connected components; the second layer
    adds degree-based component profiles; the temporal layer compares WCC
    partitions across two snapshots by stable node fingerprints. The bridge
    layer adds betweenness centrality for connector pressure. None of these
    steps depends on hand-authored semantic labels. The outlier layer adds
    nodeSimilarity over the same snapshot-local graph. The coverage layer joins
    components to action outcomes linked to the snapshot that produced them.
    The action-candidate layer compares changed component fingerprint sets to
    historical outcomes through stable SurfaceFingerprint nodes without writing
    transient probe nodes.
    """

    def connected_components(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        graph_name: str = "surface_snapshot_wcc",
        limit: int = 50,
    ) -> tuple[SurfaceComponent, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        safe_graph_name = _unique_graph_name(graph_name)
        rows = session.run(
            SURFACE_WCC_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "graph_name": safe_graph_name,
                "limit": limit,
            },
        )
        return tuple(_component_from_row(dict(row)) for row in rows)

    def component_profiles(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        graph_name: str = "surface_snapshot_component_profile",
        limit: int = 50,
    ) -> tuple[SurfaceComponentProfile, ...]:
        """Return connected components enriched with degree/delta pressure.

        This method uses two GDS algorithms over the same snapshot projection:
        WCC for component membership and degree centrality for structural
        attachment. The final score is calculated in Python from normalized
        structural metrics so it can be versioned and unit-tested outside Neo4j.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        safe_graph_name = _unique_graph_name(graph_name)
        rows = session.run(
            SURFACE_COMPONENT_PROFILE_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "graph_name": safe_graph_name,
            },
        )
        profiles = tuple(_component_profile_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                profiles,
                key=lambda item: (
                    item.structural_pressure_score,
                    item.max_novelty_score,
                    item.changed_node_count,
                    item.node_count,
                ),
                reverse=True,
            )[:limit]
        )

    def component_bridges(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        graph_name: str = "surface_snapshot_component_bridges",
        limit: int = 50,
    ) -> tuple[SurfaceComponentBridgeProfile, ...]:
        """Return components enriched with betweenness connector pressure.

        WCC gives component membership, degree gives local attachment, and
        betweenness centrality gives bridge pressure: nodes that sit on many
        shortest paths can connect otherwise separate surface shapes. The score
        is deliberately structural and label-free.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        safe_graph_name = _unique_graph_name(graph_name)
        rows = session.run(
            SURFACE_COMPONENT_BRIDGE_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "graph_name": safe_graph_name,
            },
        )
        bridge_profiles = tuple(_component_bridge_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                bridge_profiles,
                key=lambda item: (
                    item.bridge_pressure_score,
                    item.max_betweenness,
                    item.max_degree,
                    item.changed_node_count,
                    item.node_count,
                ),
                reverse=True,
            )[:limit]
        )


    def component_outliers(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        graph_name: str = "surface_snapshot_component_outliers",
        limit: int = 50,
        similarity_cutoff: float = 0.05,
        top_k: int = 20,
    ) -> tuple[SurfaceComponentOutlierProfile, ...]:
        """Return components ranked by low similarity plus fresh deltas.

        WCC gives component membership and nodeSimilarity estimates whether each
        node has neighbors with similar graph neighborhoods. Components with
        low similarity and fresh snapshot deltas are treated as structural
        outliers, not as semantic categories.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not 0.0 <= similarity_cutoff <= 1.0:
            raise ValueError("similarity_cutoff must be between 0 and 1")
        safe_graph_name = _unique_graph_name(graph_name)
        rows = session.run(
            SURFACE_COMPONENT_OUTLIER_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "graph_name": safe_graph_name,
                "similarity_cutoff": similarity_cutoff,
                "top_k": top_k,
            },
        )
        outliers = tuple(_component_outlier_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                outliers,
                key=lambda item: (
                    item.outlier_score,
                    item.low_similarity_node_count,
                    item.max_novelty_score,
                    item.node_count,
                ),
                reverse=True,
            )[:limit]
        )


    def component_coverage(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        graph_name: str = "surface_snapshot_component_coverage",
        limit: int = 50,
    ) -> tuple[SurfaceComponentCoverageProfile, ...]:
        """Return changed components ranked by low experience coverage.

        WCC gives component membership. ActionOutcome-to-SurfaceSnapshot edges
        provide the measured action history that produced the snapshot deltas.
        The result separates coverage from exploration priority: a component can
        be novel and structurally changed but still have little experience.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        safe_graph_name = _unique_graph_name(graph_name)
        rows = session.run(
            SURFACE_COMPONENT_COVERAGE_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "graph_name": safe_graph_name,
            },
        )
        coverage = tuple(_component_coverage_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                coverage,
                key=lambda item: (
                    item.exploration_priority_score,
                    item.max_novelty_score,
                    item.changed_node_count,
                    -item.coverage_score,
                    item.node_count,
                ),
                reverse=True,
            )[:limit]
        )


    def component_action_candidates(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        snapshot_id: str,
        wcc_graph_name: str = "surface_component_candidate_wcc",
        similarity_graph_name: str = "surface_component_candidate_similarity",
        probe_id: str | None = None,
        limit: int = 25,
        component_limit: int = 10,
        similarity_cutoff: float = 0.05,
    ) -> tuple[SurfaceComponentActionCandidate, ...]:
        """Rank capability/profile candidates for changed components.

        The method selects the most changed WCC components in a snapshot and
        compares their stable SurfaceFingerprint sets to historical ActionOutcome
        surface-delta fingerprints. The ranking stays shape/experience-driven
        without writing transient probe nodes into the graph database.

        ``similarity_graph_name`` and ``probe_id`` are deprecated compatibility
        parameters kept for older callers from the former GDS probe path. They
        are validated only and no longer participate in the read-only Jaccard
        scoring query.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        if component_limit <= 0:
            raise ValueError("component_limit must be positive")
        if not 0.0 <= similarity_cutoff <= 1.0:
            raise ValueError("similarity_cutoff must be between 0 and 1")
        safe_wcc_graph_name = _unique_graph_name(wcc_graph_name)
        _safe_graph_name(similarity_graph_name)
        if probe_id is not None:
            _safe_probe_id(probe_id)
        rows = session.run(
            SURFACE_COMPONENT_ACTION_CANDIDATE_CYPHER,
            {
                "program_id": program_id,
                "snapshot_id": snapshot_id,
                "wcc_graph_name": safe_wcc_graph_name,
                "limit": limit,
                "component_limit": component_limit,
                "similarity_cutoff": similarity_cutoff,
            },
        )
        candidates = tuple(_component_action_candidate_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.candidate_score,
                    item.component_attention_score,
                    item.utility_score,
                    item.sample_count,
                ),
                reverse=True,
            )[:limit]
        )


    def component_drift(
        self,
        session: Neo4jSession,
        *,
        program_id: str,
        previous_snapshot_id: str,
        current_snapshot_id: str,
        graph_name_prefix: str = "surface_snapshot_drift",
        limit: int = 50,
    ) -> tuple[SurfaceComponentDrift, ...]:
        """Return current components ranked by temporal structural drift.

        WCC is computed independently for the previous and current snapshot.
        Current components are matched to the previous component with the highest
        node-fingerprint overlap. Drift is high when overlap is low, the current
        component gained many nodes, or current deltas have high novelty.
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        if previous_snapshot_id == current_snapshot_id:
            raise ValueError("previous_snapshot_id and current_snapshot_id must differ")
        safe_prefix = _safe_graph_name(graph_name_prefix)
        previous_graph_name = _unique_graph_name(f"{safe_prefix}_previous")
        current_graph_name = _unique_graph_name(f"{safe_prefix}_current")
        rows = session.run(
            SURFACE_COMPONENT_DRIFT_CYPHER,
            {
                "program_id": program_id,
                "previous_snapshot_id": previous_snapshot_id,
                "current_snapshot_id": current_snapshot_id,
                "previous_graph_name": previous_graph_name,
                "current_graph_name": current_graph_name,
            },
        )
        drift = tuple(_component_drift_from_row(dict(row)) for row in rows)
        return tuple(
            sorted(
                drift,
                key=lambda item: (
                    item.drift_score,
                    item.max_novelty_score,
                    item.introduced_node_count,
                    item.current_node_count,
                ),
                reverse=True,
            )[:limit]
        )
