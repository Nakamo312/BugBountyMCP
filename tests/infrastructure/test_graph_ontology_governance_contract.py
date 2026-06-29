from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.infrastructure.graph_ontology_support import graph_ontology as _graph_ontology


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


def test_default_ontology_keeps_probe_labels_only_as_deprecated_legacy_schema() -> None:
    symbols = _graph_ontology()
    ontology = symbols["default_graph_ontology"]()

    nodes = {definition.label: definition for definition in ontology.node_definitions}
    relationships = {definition.relationship_type: definition for definition in ontology.relationship_definitions}
    projections = {definition.name: definition for definition in ontology.projection_definitions}

    action_probe = nodes["ActionExperienceProbe"]
    assert action_probe.maturity == "deprecated"
    assert action_probe.retention == "legacy_migration_only"
    assert action_probe.projections == ()

    surface_probe = nodes["SurfaceComponentProbe"]
    assert surface_probe.maturity == "deprecated"
    assert surface_probe.retention == "legacy_migration_only"
    assert surface_probe.projections == ()

    has_feature = relationships["HAS_OUTCOME_FEATURE"]
    assert has_feature.source_labels == ("ActionOutcome",)
    assert has_feature.target_labels == ("OutcomeFeature",)

    legacy_surface_probe_edge = relationships["HAS_SURFACE_FINGERPRINT_FEATURE"]
    assert legacy_surface_probe_edge.maturity == "deprecated"
    assert legacy_surface_probe_edge.projections == ()

    surface_projection = projections["surface_graph_math"]
    assert "SurfaceComponentProbe" not in surface_projection.node_labels
    assert "HAS_SURFACE_FINGERPRINT_FEATURE" not in surface_projection.relationship_types

    action_utility = projections["action_outcome_utility"]
    assert "ActionExperienceProbe" not in action_utility.node_labels
    assert "SurfaceComponentProbe" not in action_utility.node_labels
    assert "HAS_SURFACE_FINGERPRINT_FEATURE" not in action_utility.relationship_types
