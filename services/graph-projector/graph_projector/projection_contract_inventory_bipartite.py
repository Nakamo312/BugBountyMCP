from __future__ import annotations

from .projection_contract_models import AlgorithmFamily, ProjectionContract, _contract, _signal


BIPARTITE_PROJECTION_CONTRACTS: tuple[ProjectionContract, ...] = (
_contract(
        name="G_bipartite_endpoint_param",
        purpose="Endpoint-parameter neighborhoods for missing relation suggestions and endpoint similarity.",
        contract_version="v1",
        source_projections=(
            "G_http",
        ),
        input_facts=(
            "G_http endpoint nodes",
            "G_http parameter nodes",
            "canonical parameter normalization facts",
            "endpoint observation lineage",
        ),
        node_types=(
            "endpoint",
            "param",
        ),
        edge_types=(
            "HAS_PARAM",
        ),
        algorithm_families=(
            AlgorithmFamily.DEGREE,
            AlgorithmFamily.CENTRALITY,
            AlgorithmFamily.JACCARD_SIMILARITY,
            AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE,
        ),
        allowed_algorithms=(
            "endpoint degree",
            "param centrality",
            "common parameter neighborhoods",
            "Jaccard overlap similarity",
            "simple bipartite link prediction baseline",
        ),
        output_signals=(
            "EndpointParamSimilaritySignal",
            "ParamCentralitySignal",
            "MissingEndpointParamCandidateSignal",
        ),
        output_signal_families=(
            _signal("EndpointParamSimilaritySignal", AlgorithmFamily.JACCARD_SIMILARITY),
            _signal("ParamCentralitySignal", AlgorithmFamily.DEGREE, AlgorithmFamily.CENTRALITY),
            _signal("MissingEndpointParamCandidateSignal", AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE),
        ),
        lineage_requirements=(
            "program_id",
            "G_http projection snapshot id",
            "source endpoint ids",
            "source parameter ids",
            "normalization version",
        ),
        sensitivity_rules=(
            "parameter values are not projected",
            "secret-looking parameter names require sensitivity flags",
            "candidate edges remain advisory and must not become canonical facts automatically",
        ),
        forbidden_interpretations=(
            "id-like parameter neighborhood is not an IDOR finding",
            "predicted endpoint-param edge is not an observed request",
            "high centrality is not an action instruction",
        ),
        failure_modes=(
            "generic parameters can dominate similarity",
            "client-side parameters can be under-observed",
            "route normalization errors can move edges to the wrong endpoint",
        ),
    ),
_contract(
        name="G_bipartite_host_tech",
        purpose="Host-technology neighborhoods for clustering, same-backend hints, and coverage by technology family.",
        contract_version="v1",
        source_projections=(
            "G_asset",
        ),
        input_facts=(
            "G_asset host nodes",
            "G_asset technology nodes",
            "technology normalization facts",
            "service observation lineage",
        ),
        node_types=(
            "host",
            "technology",
        ),
        edge_types=(
            "USES_TECHNOLOGY",
        ),
        algorithm_families=(
            AlgorithmFamily.CENTRALITY,
            AlgorithmFamily.JACCARD_SIMILARITY,
            AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE,
            AlgorithmFamily.COVERAGE_SUMMARY,
        ),
        allowed_algorithms=(
            "host similarity",
            "technology centrality",
            "common technology neighborhoods",
            "simple host-technology link prediction baseline",
            "coverage by technology family",
        ),
        output_signals=(
            "HostTechnologySimilaritySignal",
            "TechnologyCoverageSignal",
            "SameBackendCandidateSignal",
        ),
        output_signal_families=(
            _signal("HostTechnologySimilaritySignal", AlgorithmFamily.JACCARD_SIMILARITY),
            _signal("TechnologyCoverageSignal", AlgorithmFamily.COVERAGE_SUMMARY),
            _signal("SameBackendCandidateSignal", AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE),
        ),
        lineage_requirements=(
            "program_id",
            "G_asset projection snapshot id",
            "source host ids",
            "source technology ids",
            "fingerprint parser version",
        ),
        sensitivity_rules=(
            "technology fingerprints are advisory and may be redacted when tied to internal hosts",
            "host labels must remain bounded by program scope",
            "same-backend candidates must remain proposals only",
        ),
        forbidden_interpretations=(
            "same technology is not same ownership proof",
            "same-backend candidate is not an exploit path",
            "technology centrality is not severity",
        ),
        failure_modes=(
            "generic server headers can create false similarity",
            "CDN/shared infrastructure can merge unrelated hosts",
            "technology versions can be stale",
        ),
    ),
_contract(
        name="G_bipartite_endpoint_object",
        purpose="Endpoint-object relationship discovery, missing observation suggestions, and object coverage.",
        contract_version="v1",
        source_projections=(
            "G_http",
        ),
        input_facts=(
            "G_http endpoint nodes",
            "object/entity extraction facts",
            "object reference observations",
            "identity/object lineage where available",
        ),
        node_types=(
            "endpoint",
            "object_type",
            "object_ref",
            "entity_shape",
        ),
        edge_types=(
            "HANDLES_OBJECT_TYPE",
            "REFERENCES_OBJECT",
            "RETURNS_ENTITY_SHAPE",
        ),
        algorithm_families=(
            AlgorithmFamily.DEGREE,
            AlgorithmFamily.JACCARD_SIMILARITY,
            AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE,
            AlgorithmFamily.COVERAGE_SUMMARY,
        ),
        allowed_algorithms=(
            "endpoint-object degree",
            "common object neighborhoods",
            "endpoint likely-handles-entity baseline",
            "object coverage summary",
        ),
        output_signals=(
            "EndpointObjectCoverageSignal",
            "MissingEndpointObjectCandidateSignal",
            "EntityShapeNeighborhoodSignal",
        ),
        output_signal_families=(
            _signal("EndpointObjectCoverageSignal", AlgorithmFamily.COVERAGE_SUMMARY),
            _signal("MissingEndpointObjectCandidateSignal", AlgorithmFamily.BIPARTITE_LINK_PREDICTION_BASELINE),
            _signal("EntityShapeNeighborhoodSignal", AlgorithmFamily.JACCARD_SIMILARITY),
        ),
        lineage_requirements=(
            "program_id",
            "G_http projection snapshot id",
            "object extraction source ids",
            "identity lineage refs where present",
            "normalization version",
        ),
        sensitivity_rules=(
            "raw object identifiers may be sensitive and should be hashed/redacted when needed",
            "identity-linked object refs must not expose principal secrets",
            "candidate object edges remain advisory missing-observation requests",
        ),
        forbidden_interpretations=(
            "object relationship is not authorization proof",
            "missing endpoint-object candidate is not a finding",
            "entity-shape similarity is not privilege boundary evidence by itself",
        ),
        failure_modes=(
            "object extraction can infer false entities from examples",
            "hashed/redacted object refs can reduce matching quality",
            "dynamic schemas can look like new object types",
        ),
    )
)
