from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.infrastructure.graph_ontology_support import graph_ontology as _graph_ontology


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
