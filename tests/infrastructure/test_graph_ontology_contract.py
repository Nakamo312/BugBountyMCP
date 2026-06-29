from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


def _graph_ontology():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.ontology import (
        GraphNodeDefinition,
        GraphOntology,
        GraphProjectionDefinition,
        GraphRelationshipDefinition,
        default_graph_ontology,
        load_graph_ontology,
    )

    return {
        "GraphNodeDefinition": GraphNodeDefinition,
        "GraphRelationshipDefinition": GraphRelationshipDefinition,
        "GraphProjectionDefinition": GraphProjectionDefinition,
        "GraphOntology": GraphOntology,
        "default_graph_ontology": default_graph_ontology,
        "load_graph_ontology": load_graph_ontology,
    }


def test_graph_ontology_describes_one_shared_graph_not_separate_graphs() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    assert ontology.name == "bug_bounty_knowledge_graph"
    assert {definition.label for definition in ontology.node_definitions} >= {
        "Program",
        "Scope",
        "Host",
        "IP",
        "ASN",
        "CIDR",
        "Service",
        "Endpoint",
        "Parameter",
        "Tool",
        "ToolRun",
        "Artifact",
        "Observation",
        "Evidence",
    }
    assert {definition.layer for definition in ontology.node_definitions} >= {
        "surface",
        "lineage",
    }


def test_node_definitions_have_identity_lineage_and_projection_membership() -> None:
    symbols = _graph_ontology()
    GraphNodeDefinition = symbols["GraphNodeDefinition"]

    definition = GraphNodeDefinition(
        label="Endpoint",
        layer="surface",
        level="L2_WEB_API",
        maturity="experimental",
        sources=("httpx", "surface_map"),
        parser_outputs=("http_observations", "surface_nodes"),
        query_templates=("endpoint_neighborhood",),
        property_vs_node_rationale="Endpoint participates in path queries and surface clustering.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Use parser confidence and evidence freshness.",
        stale_policy="Refresh last_seen from repeated observations.",
        identity={
            "graph_key": "url",
            "source_properties": ("url",),
            "key_policy": "normalized_url",
        },
        identity_properties=("program_id", "url"),
        required_properties=("program_id", "url"),
        optional_properties=("method", "status_code", "content_type"),
        source_references=("source_artifact_id", "tool_run_id"),
        projections=("asset_exposure", "endpoint_neighborhood", "evidence_path"),
        description="Web endpoint observed in scope.",
    )

    assert definition.label == "Endpoint"
    assert definition.identity_properties == ("program_id", "url")
    assert "source_artifact_id" in definition.source_references
    assert "endpoint_neighborhood" in definition.projections

    with pytest.raises(ValidationError):
        GraphNodeDefinition(
            label="Endpoint",
            layer="surface",
            level="L2_WEB_API",
            maturity="experimental",
            sources=("httpx",),
            parser_outputs=("http_observations",),
            query_templates=("endpoint_neighborhood",),
            property_vs_node_rationale="Endpoint participates in path queries.",
            retention="program_lifetime",
            sensitivity="normal",
            confidence_policy="Use parser confidence.",
            stale_policy="Refresh last_seen from repeated observations.",
            identity={
                "graph_key": "url",
                "source_properties": ("url",),
                "key_policy": "normalized_url",
            },
            identity_properties=(),
            required_properties=("program_id", "url"),
            source_references=("source_artifact_id",),
            projections=("asset_exposure",),
            description="Missing identity.",
        )


def test_relationship_definitions_bind_allowed_endpoint_labels_and_projection_membership() -> None:
    symbols = _graph_ontology()
    GraphRelationshipDefinition = symbols["GraphRelationshipDefinition"]

    definition = GraphRelationshipDefinition(
        relationship_type="PRODUCED_OBSERVATION",
        source_labels=("Artifact",),
        target_labels=("Observation",),
        level="L0_CORE",
        maturity="experimental",
        sources=("parser_output",),
        parser_outputs=("observations",),
        query_templates=("evidence_path",),
        property_vs_node_rationale="Produced observations are relationships because artifacts can yield many observations.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Use parser confidence and evidence freshness.",
        stale_policy="Refresh last_seen from repeated observations.",
        required_properties=("program_id",),
        optional_properties=("parser_version", "confidence"),
        source_references=("source_artifact_id", "tool_run_id"),
        projections=("evidence_path",),
        description="Artifact yielded a normalized observation.",
    )

    assert definition.relationship_type == "PRODUCED_OBSERVATION"
    assert definition.source_labels == ("Artifact",)
    assert definition.target_labels == ("Observation",)
    assert definition.projections == ("evidence_path",)

    with pytest.raises(ValidationError):
        GraphRelationshipDefinition(
            relationship_type="PRODUCED_OBSERVATION",
            source_labels=(),
            target_labels=("Observation",),
            level="L0_CORE",
            maturity="experimental",
            sources=("parser_output",),
            parser_outputs=("observations",),
            query_templates=("evidence_path",),
            property_vs_node_rationale="Produced observations are relationships because artifacts can yield many observations.",
            retention="program_lifetime",
            sensitivity="normal",
            confidence_policy="Use parser confidence.",
            stale_policy="Refresh last_seen from repeated observations.",
            source_references=("source_artifact_id",),
            projections=("evidence_path",),
            description="Missing source labels.",
        )


def test_named_projections_are_task_scoped_slices_of_the_shared_graph() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    projections = {definition.name: definition for definition in ontology.projection_definitions}
    assert set(projections) >= {
        "asset_exposure",
        "endpoint_neighborhood",
        "evidence_path",
    }

    asset_exposure = projections["asset_exposure"]
    assert "Host" in asset_exposure.node_labels
    assert "Endpoint" in asset_exposure.node_labels
    assert "ToolRun" not in asset_exposure.node_labels
    assert "Artifact" not in asset_exposure.node_labels

    evidence_path = projections["evidence_path"]
    assert "Artifact" in evidence_path.node_labels
    assert "Observation" in evidence_path.node_labels
    assert "Evidence" in evidence_path.node_labels
    assert "PRODUCED_OBSERVATION" in evidence_path.relationship_types

    endpoint_neighborhood = projections["endpoint_neighborhood"]
    assert "Parameter" in endpoint_neighborhood.node_labels
    assert "HAS_PARAM" in endpoint_neighborhood.relationship_types


def test_default_ontology_supports_endpoint_parameters() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    nodes = {definition.label: definition for definition in ontology.node_definitions}
    relationships = {definition.relationship_type: definition for definition in ontology.relationship_definitions}

    parameter = nodes["Parameter"]
    assert parameter.identity.graph_key == "endpoint_location_name"
    assert parameter.identity.source_properties == ("endpoint_key", "location", "name")
    assert parameter.required_properties == (
        "program_id",
        "endpoint_location_name",
        "endpoint_key",
        "location",
        "name",
    )
    assert "http_observations" in parameter.parser_outputs

    has_param = relationships["HAS_PARAM"]
    assert has_param.source_labels == ("Endpoint",)
    assert has_param.target_labels == ("Parameter",)
    assert "endpoint_neighborhood" in has_param.projections

    describes = relationships["DESCRIBES"]
    assert "Parameter" in describes.target_labels


def test_default_ontology_supports_javascript_references_to_endpoints() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    nodes = {definition.label: definition for definition in ontology.node_definitions}
    relationships = {definition.relationship_type: definition for definition in ontology.relationship_definitions}
    projections = {definition.name: definition for definition in ontology.projection_definitions}

    js_file = nodes["JSFile"]
    assert js_file.identity.graph_key == "url"
    assert js_file.required_properties == ("program_id", "url")
    assert "javascript_references" in js_file.parser_outputs

    references = relationships["REFERENCES"]
    assert references.source_labels == ("JSFile",)
    assert references.target_labels == ("Endpoint",)
    assert "endpoint_neighborhood" in references.projections
    assert "evidence_path" in references.projections

    describes = relationships["DESCRIBES"]
    assert "JSFile" in describes.target_labels

    endpoint_neighborhood = projections["endpoint_neighborhood"]
    assert "JSFile" in endpoint_neighborhood.node_labels
    assert "REFERENCES" in endpoint_neighborhood.relationship_types


def test_default_ontology_uses_host_as_domain_asset_not_separate_domain_label() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    node_labels = {definition.label for definition in ontology.node_definitions}
    relationship_types = {definition.relationship_type for definition in ontology.relationship_definitions}
    relationships = {definition.relationship_type: definition for definition in ontology.relationship_definitions}
    projections = {definition.name: definition for definition in ontology.projection_definitions}

    assert "Domain" not in node_labels
    assert "CONTAINS_DOMAIN" not in relationship_types
    assert "HAS_HOST" not in relationship_types

    scope_match = relationships["MATCHES_SCOPE"]
    assert scope_match.source_labels == ("Scope",)
    assert scope_match.target_labels == ("Host",)
    assert scope_match.parser_outputs == ("hosts",)

    asset_exposure = projections["asset_exposure"]
    assert "Domain" not in asset_exposure.node_labels
    assert "MATCHES_SCOPE" in asset_exposure.relationship_types


def test_default_ontology_uses_source_backed_network_paths() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    relationships = {definition.relationship_type: definition for definition in ontology.relationship_definitions}
    relationship_types = set(relationships)

    assert "IN_ASN" not in relationship_types

    announced_by = relationships["ANNOUNCED_BY"]
    assert announced_by.source_labels == ("CIDR",)
    assert announced_by.target_labels == ("ASN",)
    assert announced_by.parser_outputs == ("cidrs",)

    exposes_service = relationships["EXPOSES_SERVICE"]
    assert exposes_service.source_labels == ("IP",)
    assert exposes_service.target_labels == ("Service",)
    assert exposes_service.parser_outputs == ("services",)


def test_default_graph_ontology_is_loaded_from_yaml_next_to_module() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    ontology_path = Path("services/graph-projector/graph_projector/ontology.yaml")
    assert ontology_path.exists()
    assert ontology.name == "bug_bounty_knowledge_graph"



def test_load_graph_ontology_validates_custom_yaml_references(tmp_path: Path) -> None:
    symbols = _graph_ontology()
    load_graph_ontology = symbols["load_graph_ontology"]

    valid_yaml = tmp_path / "ontology.yaml"
    valid_yaml.write_text(
        """
name: custom_graph
nodes:
  - label: Host
    layer: surface
    level: L1_INFRASTRUCTURE
    maturity: experimental
    sources: [dnsx]
    parser_outputs: [hosts]
    query_templates: [asset_exposure]
    property_vs_node_rationale: Host participates in path queries.
    retention: program_lifetime
    sensitivity: normal
    confidence_policy: Use parser confidence.
    stale_policy: Refresh last_seen from observations.
    identity:
      graph_key: hostname
      source_properties: [hostname]
      key_policy: lower_fqdn
    identity_properties: [program_id, hostname]
    required_properties: [program_id, hostname]
    projections: [asset_exposure]
    description: Host node.
  - label: IP
    layer: surface
    level: L1_INFRASTRUCTURE
    maturity: experimental
    sources: [dnsx]
    parser_outputs: [ip_addresses]
    query_templates: [asset_exposure]
    property_vs_node_rationale: IP participates in network path queries.
    retention: program_lifetime
    sensitivity: normal
    confidence_policy: Use parser confidence.
    stale_policy: Refresh last_seen from observations.
    identity:
      graph_key: address
      source_properties: [address]
      key_policy: canonical_ip_address
    identity_properties: [program_id, address]
    required_properties: [program_id, address]
    projections: [asset_exposure]
    description: IP node.
relationships:
  - relationship_type: RESOLVES_TO
    source_labels: [Host]
    target_labels: [IP]
    level: L1_INFRASTRUCTURE
    maturity: experimental
    sources: [dnsx]
    parser_outputs: [host_ips]
    query_templates: [asset_exposure]
    property_vs_node_rationale: Resolution links host and IP assets.
    retention: program_lifetime
    sensitivity: normal
    confidence_policy: Use parser confidence.
    stale_policy: Refresh last_seen from observations.
    projections: [asset_exposure]
    description: Host resolves to IP.
projections:
  - name: asset_exposure
    level: L1_INFRASTRUCTURE
    node_labels: [Host, IP]
    relationship_types: [RESOLVES_TO]
    query_templates: [asset_exposure]
    expected_output: Test asset exposure slice.
    use_case: Test projection.
    description: Test slice.
""".strip(),
        encoding="utf-8",
    )

    ontology = load_graph_ontology(valid_yaml)
    assert ontology.name == "custom_graph"
    assert [node.label for node in ontology.node_definitions] == ["Host", "IP"]

    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text(
        """
name: invalid_graph
nodes:
  - label: Host
    layer: surface
    level: L1_INFRASTRUCTURE
    maturity: experimental
    sources: [dnsx]
    parser_outputs: [hosts]
    query_templates: [asset_exposure]
    property_vs_node_rationale: Host participates in path queries.
    retention: program_lifetime
    sensitivity: normal
    confidence_policy: Use parser confidence.
    stale_policy: Refresh last_seen from observations.
    identity_properties: [program_id, hostname]
    required_properties: [program_id, hostname]
    projections: [asset_exposure]
    description: Host node.
relationships:
  - relationship_type: RESOLVES_TO
    source_labels: [Host]
    target_labels: [Missing]
    level: L1_INFRASTRUCTURE
    maturity: experimental
    sources: [dnsx]
    parser_outputs: [host_ips]
    query_templates: [asset_exposure]
    property_vs_node_rationale: Resolution links host and IP assets.
    retention: program_lifetime
    sensitivity: normal
    confidence_policy: Use parser confidence.
    stale_policy: Refresh last_seen from observations.
    projections: [asset_exposure]
    description: Invalid edge.
projections:
  - name: asset_exposure
    level: L1_INFRASTRUCTURE
    node_labels: [Host]
    relationship_types: [RESOLVES_TO]
    query_templates: [asset_exposure]
    expected_output: Test asset exposure slice.
    use_case: Test projection.
    description: Test slice.
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_graph_ontology(invalid_yaml)


def test_node_definitions_carry_governance_metadata() -> None:
    symbols = _graph_ontology()
    GraphNodeDefinition = symbols["GraphNodeDefinition"]

    definition = GraphNodeDefinition(
        label="Endpoint",
        layer="surface",
        level="L2_WEB_API",
        maturity="experimental",
        identity={
            "graph_key": "url",
            "source_properties": ("url",),
            "key_policy": "normalized_url",
        },
        identity_properties=("program_id", "url"),
        required_properties=("program_id", "url"),
        optional_properties=("method", "status_code", "content_type"),
        source_references=("source_artifact_id", "tool_run_id"),
        sources=("httpx", "surface_map"),
        parser_outputs=("http_observations", "surface_nodes"),
        query_templates=("endpoint_neighborhood", "hidden_endpoints_from_js"),
        property_vs_node_rationale="Endpoint participates in path queries and surface clustering.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Use parser confidence and evidence freshness.",
        stale_policy="Refresh last_seen from repeated observations.",
        projections=("asset_exposure", "endpoint_neighborhood", "evidence_path"),
        description="Web endpoint observed in scope.",
    )

    assert definition.level == "L2_WEB_API"
    assert definition.maturity == "experimental"
    assert "surface_map" in definition.sources
    assert "http_observations" in definition.parser_outputs
    assert "endpoint_neighborhood" in definition.query_templates
    assert definition.property_vs_node_rationale
    assert definition.retention == "program_lifetime"
    assert definition.sensitivity == "normal"
    assert definition.confidence_policy
    assert definition.stale_policy



def test_relationship_definitions_carry_governance_metadata() -> None:
    symbols = _graph_ontology()
    GraphRelationshipDefinition = symbols["GraphRelationshipDefinition"]

    definition = GraphRelationshipDefinition(
        relationship_type="RESOLVES_TO",
        source_labels=("Host",),
        target_labels=("IP",),
        level="L1_INFRASTRUCTURE",
        maturity="experimental",
        required_properties=("program_id",),
        optional_properties=("first_seen", "last_seen", "confidence"),
        source_references=("source_artifact_id", "tool_run_id"),
        sources=("dnsx", "amass"),
        parser_outputs=("host_ips",),
        query_templates=("asset_exposure", "asn_cidr_asset_expansion"),
        property_vs_node_rationale="Resolution is a relationship because it links host assets to IP assets.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Keep max confidence and evidence-backed first_seen/last_seen.",
        stale_policy="Mark stale when the host stops resolving to the IP.",
        projections=("asset_exposure", "endpoint_neighborhood"),
        description="Host resolves to IP address.",
    )

    assert definition.level == "L1_INFRASTRUCTURE"
    assert definition.maturity == "experimental"
    assert "dnsx" in definition.sources
    assert definition.parser_outputs == ("host_ips",)
    assert "asset_exposure" in definition.query_templates
    assert definition.confidence_policy
    assert definition.stale_policy



def test_projection_definitions_carry_governance_metadata() -> None:
    symbols = _graph_ontology()
    GraphProjectionDefinition = symbols["GraphProjectionDefinition"]

    definition = GraphProjectionDefinition(
        name="endpoint_neighborhood",
        level="L2_WEB_API",
        node_labels=("Host", "Service", "Endpoint"),
        relationship_types=("EXPOSES_SERVICE", "HAS_ENDPOINT"),
        query_templates=("endpoint_neighborhood",),
        expected_output="Bounded neighborhood around an endpoint for agent reasoning.",
        use_case="Inspect endpoint-adjacent assets without traversing the whole graph.",
        description="Endpoint-centered graph slice.",
    )

    assert definition.level == "L2_WEB_API"
    assert definition.query_templates == ("endpoint_neighborhood",)
    assert definition.expected_output.startswith("Bounded neighborhood")



def test_default_ontology_definitions_include_governance_metadata() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    allowed_maturity = {"candidate", "experimental", "stable", "deprecated"}
    allowed_levels = {
        "L0_CORE",
        "L1_INFRASTRUCTURE",
        "L2_WEB_API",
        "L3_TECH_SUPPLY_CHAIN",
        "L4_OSINT_CLOUD_EXPOSURE",
        "L5_RESEARCH",
    }

    for node in ontology.node_definitions:
        assert node.maturity in allowed_maturity
        assert node.level in allowed_levels
        assert node.sources
        assert node.parser_outputs
        assert node.query_templates
        assert node.property_vs_node_rationale
        assert node.retention
        assert node.sensitivity
        assert node.confidence_policy
        assert node.stale_policy

    for relationship in ontology.relationship_definitions:
        assert relationship.maturity in allowed_maturity
        assert relationship.level in allowed_levels
        assert relationship.sources
        assert relationship.parser_outputs
        assert relationship.query_templates
        assert relationship.property_vs_node_rationale
        assert relationship.retention
        assert relationship.sensitivity
        assert relationship.confidence_policy
        assert relationship.stale_policy

    for projection in ontology.projection_definitions:
        assert projection.level in allowed_levels
        assert projection.query_templates
        assert projection.expected_output


def test_node_definitions_carry_explicit_graph_identity_policy() -> None:
    symbols = _graph_ontology()
    GraphNodeDefinition = symbols["GraphNodeDefinition"]

    definition = GraphNodeDefinition(
        label="Endpoint",
        layer="surface",
        level="L2_WEB_API",
        maturity="experimental",
        identity={
            "graph_key": "service_method_normalized_path",
            "source_properties": ("service_key", "method", "normalized_path"),
            "key_policy": "service_method_normalized_path",
        },
        identity_properties=("program_id", "service_key", "method", "normalized_path"),
        required_properties=("program_id", "service_key", "method", "normalized_path"),
        optional_properties=("status_code", "content_type"),
        source_references=("source_artifact_id", "tool_run_id"),
        sources=("httpx", "surface_map"),
        parser_outputs=("endpoints", "surface_nodes"),
        query_templates=("endpoint_neighborhood",),
        property_vs_node_rationale="Endpoint participates in path queries and surface clustering.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Use parser confidence and evidence freshness.",
        stale_policy="Refresh last_seen from repeated observations.",
        projections=("asset_exposure", "endpoint_neighborhood", "evidence_path"),
        description="Web endpoint observed in scope.",
    )

    assert definition.identity.graph_key == "service_method_normalized_path"
    assert definition.identity.source_properties == ("service_key", "method", "normalized_path")
    assert definition.identity.key_policy == "service_method_normalized_path"


def test_graph_identity_policy_rejects_empty_values() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.ontology import GraphIdentityPolicy

    with pytest.raises(ValidationError):
        GraphIdentityPolicy(
            graph_key="",
            source_properties=("hostname",),
            key_policy="lower_fqdn",
        )

    with pytest.raises(ValidationError):
        GraphIdentityPolicy(
            graph_key="hostname",
            source_properties=(),
            key_policy="lower_fqdn",
        )

    with pytest.raises(ValidationError):
        GraphIdentityPolicy(
            graph_key="hostname",
            source_properties=("hostname",),
            key_policy=" ",
        )


def test_default_ontology_nodes_define_explicit_graph_identity_policy() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    policies_by_label = {node.label: node.identity for node in ontology.node_definitions}

    assert policies_by_label["Host"].graph_key == "hostname"
    assert policies_by_label["Host"].source_properties == ("hostname",)
    assert policies_by_label["Host"].key_policy == "lower_fqdn"
    assert policies_by_label["IP"].key_policy == "canonical_ip_address"
    assert policies_by_label["Service"].key_policy == "host_port_protocol"
    assert policies_by_label["Endpoint"].key_policy == "service_method_normalized_path"

    for node in ontology.node_definitions:
        assert node.identity.graph_key
        assert node.identity.source_properties
        assert node.identity.key_policy
        assert node.identity.graph_key in node.required_properties



def test_stable_node_definition_requires_promotion_criteria() -> None:
    symbols = _graph_ontology()
    GraphNodeDefinition = symbols["GraphNodeDefinition"]

    common = dict(
        label="Host",
        layer="surface",
        level="L1_INFRASTRUCTURE",
        maturity="stable",
        identity={
            "graph_key": "hostname",
            "source_properties": ("hostname",),
            "key_policy": "lower_fqdn",
        },
        identity_properties=("program_id", "hostname"),
        required_properties=("program_id", "hostname"),
        source_references=("source_artifact_id", "tool_run_id"),
        sources=("dnsx",),
        parser_outputs=("hosts",),
        query_templates=("asset_exposure",),
        property_vs_node_rationale="Host is a node because it participates in asset path queries.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Keep max confidence across repeated observations.",
        stale_policy="Mark stale when evidence stops reproducing the fact.",
        projections=("asset_exposure",),
        description="Stable host node.",
    )

    with pytest.raises(ValidationError):
        GraphNodeDefinition(**common)

    definition = GraphNodeDefinition(
        **common,
        promotion={
            "producer": "InfrastructureGraphFactProducer",
            "query_template": "asset_exposure",
            "idempotent_upsert_test": "test_graph_fact_writer_merges_nodes_and_edges_without_creating_edge_endpoints",
            "evidence_lineage_example": "dnsx artifact -> parser output -> Host GraphNodeFact",
            "identity_key": "program_id + key",
            "constraints": "Neo4j unique constraint on Host(program_id, key)",
            "graph_facts": "Host GraphNodeFact emitted from dnsx parser output",
            "rebuild_support": "Rebuilt from PostgreSQL canonical facts and raw artifact metadata",
            "dashboard_or_search_representation": "Host appears in asset exposure dashboard/search",
        },
    )

    assert definition.promotion.producer == "InfrastructureGraphFactProducer"
    assert definition.promotion.query_template == "asset_exposure"


def test_experimental_definition_does_not_require_promotion_criteria() -> None:
    symbols = _graph_ontology()
    GraphRelationshipDefinition = symbols["GraphRelationshipDefinition"]

    definition = GraphRelationshipDefinition(
        relationship_type="RESOLVES_TO",
        source_labels=("Host",),
        target_labels=("IP",),
        level="L1_INFRASTRUCTURE",
        maturity="experimental",
        required_properties=("program_id",),
        source_references=("source_artifact_id", "tool_run_id"),
        sources=("dnsx",),
        parser_outputs=("host_ips",),
        query_templates=("asset_exposure",),
        property_vs_node_rationale="Resolution is a relationship because it links host and IP assets.",
        retention="program_lifetime",
        sensitivity="normal",
        confidence_policy="Keep max confidence across repeated observations.",
        stale_policy="Mark stale when evidence stops reproducing the edge.",
        projections=("asset_exposure",),
        description="Host resolves to IP.",
    )

    assert definition.maturity == "experimental"
    assert definition.promotion is None
