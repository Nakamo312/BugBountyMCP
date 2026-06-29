from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .surface_gds_scores import (
    SURFACE_GDS_CALIBRATION_STATUS,
    SURFACE_GDS_RANKER_KIND,
    SURFACE_GDS_SCORE_FORMULA_VERSION,
)


class Neo4jSession(Protocol):
    def run(self, query: str, parameters: dict[str, object] | None = None) -> Any: ...


@dataclass(frozen=True)
class SurfaceComponent:
    component_id: int
    node_count: int
    avg_novelty_score: float
    max_novelty_score: int


@dataclass(frozen=True)
class SurfaceComponentProfile:
    """Graph-derived profile for one connected surface component.

    The profile intentionally stays structural: it aggregates graph membership,
    degree centrality and snapshot deltas. It does not label the component as an
    API/admin/auth area and does not depend on endpoint word lists.
    """

    component_id: int
    node_count: int
    changed_node_count: int
    avg_novelty_score: float
    max_novelty_score: int
    avg_degree: float
    max_degree: float
    novelty_density: float
    structural_pressure_score: int



@dataclass(frozen=True)
class SurfaceComponentDrift:
    """Temporal movement of one current component relative to a prior snapshot.

    The match is structural: components are compared by stable node
    fingerprints shared across two snapshot-local WCC partitions. A high score
    means the current component is less explainable by the previous partition
    and/or concentrates fresh surface deltas. No semantic labels are used.
    """

    current_component_id: int
    previous_component_id: int | None
    current_node_count: int
    previous_node_count: int
    shared_node_count: int
    introduced_node_count: int
    removed_node_count: int
    jaccard_similarity: float
    avg_novelty_score: float
    max_novelty_score: int
    drift_score: int




@dataclass(frozen=True)
class SurfaceComponentBridgeProfile:
    """Bridge/connector pressure for one connected surface component.

    The profile is graph-structural: betweenness centrality estimates whether
    nodes in the component lie on many shortest paths. High values mean the
    component contains connector vertices in the shape graph. No URL words or
    domain labels participate in the calculation.
    """

    component_id: int
    node_count: int
    changed_node_count: int
    avg_betweenness: float
    max_betweenness: float
    avg_degree: float
    max_degree: float
    novelty_density: float
    max_novelty_score: int
    bridge_pressure_score: int


@dataclass(frozen=True)
class SurfaceComponentOutlierProfile:
    """Similarity outlier profile for one connected surface component.

    The profile is structural: nodeSimilarity estimates how much nodes in the
    component resemble other nodes in the same snapshot-local shape graph. A
    high outlier score means the component has low neighborhood similarity and
    concentrates fresh deltas. No endpoint words or handwritten categories are
    used.
    """

    component_id: int
    node_count: int
    changed_node_count: int
    avg_similarity: float
    max_similarity: float
    low_similarity_node_count: int
    novelty_density: float
    max_novelty_score: int
    outlier_score: int


@dataclass(frozen=True)
class SurfaceComponentCoverageProfile:
    """Experience coverage for one connected surface component.

    Coverage joins the structural component partition with action outcomes that
    produced the snapshot deltas inside the component. It measures whether a
    changed region has already been exercised by prior actions and feedback,
    without assigning semantic labels to the component.
    """

    component_id: int
    node_count: int
    changed_node_count: int
    action_outcome_count: int
    positive_outcome_count: int
    stop_outcome_count: int
    avg_outcome_utility: float
    novelty_density: float
    max_novelty_score: int
    coverage_score: int
    exploration_priority_score: int


@dataclass(frozen=True)
class SurfaceComponentActionCandidate:
    """Experience-ranked action candidate for a changed surface component.

    The component fingerprint set is compared to historical ActionOutcome
    surface-delta fingerprints. The candidate is still advisory:
    it names only the learned capability/profile pair and never bypasses the
    action service, policy, scope, approval, or budget checks.
    """

    component_id: int
    node_count: int
    changed_node_count: int
    max_novelty_score: int
    capability_id: str
    profile_id: str
    sample_count: int
    avg_similarity: float
    avg_information_gain_score: float
    human_positive_rate: float
    human_stop_rate: float
    utility_score: float
    component_attention_score: int
    candidate_score: int
    ranker_kind: str = SURFACE_GDS_RANKER_KIND
    calibration_status: str = SURFACE_GDS_CALIBRATION_STATUS
    score_formula_version: str = SURFACE_GDS_SCORE_FORMULA_VERSION
    score_features: dict[str, object] = field(default_factory=dict)
