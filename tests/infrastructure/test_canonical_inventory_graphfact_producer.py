from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.canonical_inventory import (
        CanonicalInventoryGraphFactProducer,
        canonical_inventory_dedupe_key,
    )

    return CanonicalInventoryGraphFactProducer, canonical_inventory_dedupe_key


def _row(**overrides):
    values = {
        "program_id": uuid4(),
        "host_id": uuid4(),
        "hostname": "API.EXAMPLE.COM.",
        "ip_id": uuid4(),
        "ip_address": "203.0.113.10",
        "host_ip_source": "dnsx",
        "service_id": uuid4(),
        "service_scheme": "https",
        "service_port": 443,
        "technologies": {"nginx": True},
    }
    values.update(overrides)
    return values


def _node_set(batch):
    return {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}


def _edge_set(batch):
    return {
        (fact.src_kind, fact.src_key, fact.edge_kind, fact.dst_kind, fact.dst_key)
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }


def test_canonical_inventory_producer_projects_host_ip_service_without_artifact_lineage() -> None:
    CanonicalInventoryGraphFactProducer, _ = _symbols()
    row = _row()

    batch = CanonicalInventoryGraphFactProducer().produce([row])

    assert batch is not None
    assert batch.produced_by == "canonical-inventory"
    nodes = _node_set(batch)
    edges = _edge_set(batch)
    assert ("Host", "api.example.com") in nodes
    assert ("IP", "203.0.113.10") in nodes
    assert ("Service", "api.example.com:443/https") in nodes
    assert ("Host", "api.example.com", "RESOLVES_TO", "IP", "203.0.113.10") in edges
    assert ("IP", "203.0.113.10", "EXPOSES_SERVICE", "Service", "api.example.com:443/https") in edges
    assert all(fact.producer == "canonical-inventory" for fact in batch.facts)
    assert all(fact.source_artifact_id is None for fact in batch.facts)
    assert all(fact.tool_run_id is None for fact in batch.facts)


def test_canonical_inventory_producer_can_project_host_ip_without_service() -> None:
    CanonicalInventoryGraphFactProducer, _ = _symbols()

    batch = CanonicalInventoryGraphFactProducer().produce(
        [_row(service_id=None, service_scheme=None, service_port=None, technologies=None)]
    )

    assert batch is not None
    assert ("Service", "api.example.com:443/https") not in _node_set(batch)
    assert ("Host", "api.example.com", "RESOLVES_TO", "IP", "203.0.113.10") in _edge_set(batch)


def test_canonical_inventory_producer_allows_network_only_rows_without_host_or_ip() -> None:
    CanonicalInventoryGraphFactProducer, _ = _symbols()

    batch = CanonicalInventoryGraphFactProducer().produce([
        _row(
            hostname=None,
            ip_address=None,
            service_id=None,
            service_scheme=None,
            service_port=None,
            cidr="203.0.113.0/24",
            asn_number=64500,
            asn_name="EXAMPLE-NET",
            asn_country="US",
        )
    ])

    assert batch is not None
    nodes = _node_set(batch)
    edges = _edge_set(batch)
    assert ("ASN", "AS64500") in nodes
    assert ("CIDR", "203.0.113.0/24") in nodes
    assert ("CIDR", "203.0.113.0/24", "ANNOUNCED_BY", "ASN", "AS64500") in edges


def test_canonical_inventory_producer_skips_empty_rows() -> None:
    CanonicalInventoryGraphFactProducer, _ = _symbols()

    assert CanonicalInventoryGraphFactProducer().produce([
        _row(
            hostname=None,
            ip_address=None,
            service_id=None,
            service_scheme=None,
            service_port=None,
            cidr=None,
            asn_number=None,
        )
    ]) is None


def test_canonical_inventory_dedupe_key_is_per_program_and_parser_version() -> None:
    _, dedupe_key = _symbols()
    program_id = uuid4()

    assert dedupe_key(program_id, "canonical-inventory.v1") == (
        f"canonical-inventory:{program_id}:canonical-inventory.v1"
    )
