from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.gds_readiness import evaluate_gds_readiness
    from graph_projector.query_templates import (
        GraphQueryTemplate,
        default_query_template_registry,
    )

    return GraphQueryTemplate, default_query_template_registry, evaluate_gds_readiness


def test_default_query_templates_are_program_scoped_read_only_and_do_not_use_gds() -> None:
    _, default_query_template_registry, _ = _symbols()
    registry = default_query_template_registry()

    for name in (
        "endpoint_neighborhood",
        "asset_exposure",
        "hidden_endpoints_from_js",
        "exposed_services_by_technology",
        "evidence_path",
        "hypothesis_evidence_paths",
    ):
        template = registry.get(name)

        assert "program_id" in template.required_parameters
        assert "$program_id" in template.cypher
        assert "LIMIT $limit" in template.cypher
        assert "gds." not in template.cypher.lower()
        assert template.is_read_only is True


def test_query_template_render_requires_declared_parameters_only() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("endpoint_neighborhood")

    rendered = template.render({"program_id": "program-1", "identity_key": "node:Endpoint:x", "limit": 25})

    assert rendered.cypher == template.cypher
    assert rendered.parameters == {
        "program_id": "program-1",
        "identity_key": "node:Endpoint:x",
        "limit": 25,
    }

    with pytest.raises(ValueError, match="missing required graph query parameter"):
        template.render({"identity_key": "node:Endpoint:x", "limit": 25})

    with pytest.raises(ValueError, match="unsupported graph query parameter"):
        template.render(
            {
                "program_id": "program-1",
                "identity_key": "node:Endpoint:x",
                "limit": 25,
                "unsafe": "value",
            }
        )


def test_evidence_path_template_requires_one_graph_identity() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("evidence_path")

    rendered = template.render(
        {
            "program_id": "program-1",
            "identity_key": "node:Endpoint:api.example.test:/v1/users",
            "limit": 10,
        }
    )

    assert rendered.parameters == {
        "program_id": "program-1",
        "identity_key": "node:Endpoint:api.example.test:/v1/users",
        "limit": 10,
    }
    assert "PRODUCED_OBSERVATION" in rendered.cypher
    assert "DESCRIBES" in rendered.cypher


def test_exposed_services_by_technology_template_supports_optional_filter() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("exposed_services_by_technology")

    rendered = template.render(
        {
            "program_id": "program-1",
            "technology": "nginx",
            "limit": 20,
        }
    )

    assert rendered.parameters == {
        "program_id": "program-1",
        "technology": "nginx",
        "limit": 20,
    }
    assert "$technology" in rendered.cypher
    assert "toLower" in rendered.cypher


def test_hypothesis_evidence_paths_template_stays_read_only_without_finding_promotion() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("hypothesis_evidence_paths")

    rendered = template.render({"program_id": "program-1", "hypothesis_id": "hyp-1", "limit": 5})

    assert rendered.parameters == {"program_id": "program-1", "hypothesis_id": "hyp-1", "limit": 5}
    assert "Finding" not in rendered.cypher
    assert "PROMOTED" not in rendered.cypher




def test_query_template_render_bounds_limit_and_defaults_when_omitted() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("endpoint_neighborhood")

    rendered = template.render({"program_id": "program-1", "identity_key": "node:Endpoint:x"})

    assert rendered.parameters["limit"] == template.max_rows

    capped = template.render({"program_id": "program-1", "identity_key": "node:Endpoint:x", "limit": 10_000})

    assert capped.parameters["limit"] == template.max_rows

    with pytest.raises(ValueError, match="positive integer"):
        template.render({"program_id": "program-1", "identity_key": "node:Endpoint:x", "limit": 0})

    with pytest.raises(ValueError, match="positive integer"):
        template.render({"program_id": "program-1", "identity_key": "node:Endpoint:x", "limit": True})


def test_query_template_render_rejects_null_empty_or_unsupported_parameter_values() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("endpoint_neighborhood")

    with pytest.raises(ValueError, match="must not be null"):
        template.render({"program_id": None, "identity_key": "node:Endpoint:x", "limit": 25})

    with pytest.raises(ValueError, match="must not be empty"):
        template.render({"program_id": "   ", "identity_key": "node:Endpoint:x", "limit": 25})

    with pytest.raises(ValueError, match="unsupported graph query parameter type"):
        template.render({"program_id": "program-1", "identity_key": {"nested": "value"}, "limit": 25})

    with pytest.raises(ValueError, match="too long"):
        template.render({"program_id": "program-1", "identity_key": "x" * 2049, "limit": 25})

def test_query_template_rejects_write_or_gds_cypher() -> None:
    GraphQueryTemplate, *_ = _symbols()

    with pytest.raises(ValueError, match="read-only"):
        GraphQueryTemplate(
            name="bad_write",
            description="bad",
            cypher="MATCH (n) DELETE n",
            required_parameters=("program_id",),
            optional_parameters=("limit",),
        )

    with pytest.raises(ValueError, match="GDS"):
        GraphQueryTemplate(
            name="bad_gds",
            description="bad",
            cypher="CALL gds.pageRank.stream('all') YIELD nodeId RETURN nodeId LIMIT $limit",
            required_parameters=("program_id",),
            optional_parameters=("limit",),
        )


def test_gds_readiness_requires_rebuild_support_and_safe_query_templates() -> None:
    _, default_query_template_registry, evaluate_gds_readiness = _symbols()

    ready = evaluate_gds_readiness(
        query_templates=default_query_template_registry(),
        rebuild_supported=True,
    )
    missing_rebuild = evaluate_gds_readiness(
        query_templates=default_query_template_registry(),
        rebuild_supported=False,
    )

    assert ready.ready is True
    assert ready.missing_query_templates == ()
    assert missing_rebuild.ready is False
    assert missing_rebuild.reasons == ("graph rebuild command is not available",)


def test_program_exposure_topology_uses_island_tolerant_subqueries() -> None:
    _, default_query_template_registry, _ = _symbols()
    template = default_query_template_registry().get("program_exposure_topology")

    assert "CALL {" in template.cypher
    assert "OPTIONAL MATCH (program:Program" in template.cypher
    assert "topology_nodes" in template.cypher
    assert "collect(host_ip_path)[0..$limit]" in template.cypher
    assert "collect(ip_cidr_path)[0..$limit]" in template.cypher
    assert "collect(cidr_asn_path)[0..$limit]" in template.cypher
    assert "MATCH infra_path = (:ASN" not in template.cypher
    assert "collect(observation_evidence_path)[0..$limit]" in template.cypher
    assert "surface_endpoint_path" in template.cypher
    assert "REPRESENTS" in template.cypher
    assert "HAS_REQUEST_SHAPE" in template.cypher
