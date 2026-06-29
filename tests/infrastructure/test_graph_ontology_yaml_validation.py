from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.infrastructure.graph_ontology_support import graph_ontology as _graph_ontology


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
