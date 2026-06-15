from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest


def _symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.http_observations import (
        HttpObservationGraphFactProducer,
        http_observations_dedupe_key,
        service_key,
        service_method_normalized_path_key,
    )

    return (
        HttpObservationGraphFactProducer,
        http_observations_dedupe_key,
        service_key,
        service_method_normalized_path_key,
    )


def _observation_row(**overrides):
    program_id = overrides.pop("program_id", uuid4())
    run_id = overrides.pop("run_id", uuid4())
    raw_artifact_id = overrides.pop("raw_artifact_id", uuid4())
    row = {
        "observation_id": uuid4(),
        "program_id": program_id,
        "run_id": run_id,
        "raw_artifact_id": raw_artifact_id,
        "source_tool": "httpx",
        "method": "GET",
        "url": "https://api.example.com/v1/users/123",
        "status_code": 200,
        "content_type": "application/json",
        "observed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "endpoint_id": uuid4(),
        "path": "/v1/users/123",
        "normalized_path": "/v1/users/{id}",
        "host_id": uuid4(),
        "hostname": "api.example.com",
        "service_id": uuid4(),
        "scheme": "https",
        "port": 443,
        "ip_id": uuid4(),
        "ip_address": "203.0.113.10",
    }
    row.update(overrides)
    return row


def test_http_observation_producer_builds_asset_graphfacts() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()
    row = _observation_row()

    batch = HttpObservationGraphFactProducer(parser_version="http-observations.v1").produce([row])

    assert batch is not None
    assert batch.program_id == row["program_id"]
    assert batch.produced_by == "httpx-observation-producer"
    assert batch.parser_version == "http-observations.v1"

    svc_key = "api.example.com:443/https"
    endpoint_key = "api.example.com:443/https:GET:/v1/users/{id}"
    node_facts = {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}
    assert ("Host", "api.example.com") in node_facts
    assert ("IP", "203.0.113.10") in node_facts
    assert ("Service", svc_key) in node_facts
    assert ("Endpoint", endpoint_key) in node_facts

    host_fact = next(fact for fact in batch.facts if getattr(fact, "kind", None) == "Host")
    service_fact = next(fact for fact in batch.facts if getattr(fact, "kind", None) == "Service")
    endpoint_fact = next(fact for fact in batch.facts if getattr(fact, "kind", None) == "Endpoint")
    assert host_fact.properties == {"hostname": "api.example.com"}
    assert service_fact.properties["service_key"] == svc_key
    assert service_fact.properties["port"] == 443
    assert service_fact.properties["scheme"] == "https"
    assert endpoint_fact.properties["service_key"] == svc_key
    assert endpoint_fact.properties["service_method_normalized_path"] == endpoint_key
    assert endpoint_fact.properties["method"] == "GET"
    assert endpoint_fact.properties["normalized_path"] == "/v1/users/{id}"
    assert endpoint_fact.properties["status_code"] == 200
    assert endpoint_fact.properties["content_type"] == "application/json"
    assert endpoint_fact.properties["url"] == "https://api.example.com/v1/users/123"

    edge_facts = {
        (fact.src_kind, fact.src_key, fact.edge_kind, fact.dst_kind, fact.dst_key)
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }
    assert ("Host", "api.example.com", "RESOLVES_TO", "IP", "203.0.113.10") in edge_facts
    assert ("IP", "203.0.113.10", "EXPOSES_SERVICE", "Service", svc_key) in edge_facts
    assert ("Service", svc_key, "HAS_ENDPOINT", "Endpoint", endpoint_key) in edge_facts

    for fact in batch.facts:
        assert fact.program_id == row["program_id"]
        assert fact.producer == "httpx"
        assert fact.source_artifact_id == row["raw_artifact_id"]
        assert fact.tool_run_id == row["run_id"]
        assert fact.confidence == 1.0


def test_http_observation_producer_deduplicates_repeated_rows() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()
    row = _observation_row()

    batch = HttpObservationGraphFactProducer().produce([row, dict(row, observation_id=uuid4())])

    assert batch is not None
    assert len(batch.facts) == 7
    identity_keys = [fact.identity_key for fact in batch.facts]
    assert len(identity_keys) == len(set(identity_keys))


def test_http_observation_producer_preserves_distinct_lineage_for_same_graph_identity() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()
    program_id = uuid4()
    first_raw_artifact_id = uuid4()
    second_raw_artifact_id = uuid4()
    first_run_id = uuid4()
    second_run_id = uuid4()
    first = _observation_row(
        program_id=program_id,
        raw_artifact_id=first_raw_artifact_id,
        run_id=first_run_id,
    )
    second = dict(
        first,
        observation_id=uuid4(),
        raw_artifact_id=second_raw_artifact_id,
        run_id=second_run_id,
    )

    batch = HttpObservationGraphFactProducer().produce([first, second])

    assert batch is not None
    assert len(batch.facts) == 14
    endpoint_facts = [
        fact
        for fact in batch.facts
        if getattr(fact, "kind", None) == "Endpoint"
        and fact.key == "api.example.com:443/https:GET:/v1/users/{id}"
    ]
    assert len(endpoint_facts) == 2
    assert {
        (fact.source_artifact_id, fact.tool_run_id)
        for fact in endpoint_facts
    } == {
        (first_raw_artifact_id, first_run_id),
        (second_raw_artifact_id, second_run_id),
    }


def test_http_observation_producer_skips_rows_without_run_or_artifact_lineage() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()

    assert HttpObservationGraphFactProducer().produce([_observation_row(run_id=None)]) is None
    assert HttpObservationGraphFactProducer().produce([_observation_row(raw_artifact_id=None)]) is None


def test_http_observation_producer_rejects_mixed_program_rows() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()

    with pytest.raises(ValueError, match="program_id"):
        HttpObservationGraphFactProducer().produce([_observation_row(), _observation_row()])


def test_http_observation_producer_does_not_project_raw_response_payloads() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()
    row = _observation_row(
        response_body="secret body",
        headers={"authorization": "Bearer secret"},
        raw_output="full httpx output",
    )

    batch = HttpObservationGraphFactProducer().produce([row])

    assert batch is not None
    for fact in batch.facts:
        assert "response_body" not in fact.properties
        assert "headers" not in fact.properties
        assert "raw_output" not in fact.properties


def test_http_observation_key_helpers_match_ontology_identity_inputs() -> None:
    _, _, service_key_fn, endpoint_key_fn = _symbols()

    svc_key = service_key_fn(hostname=" API.Example.COM.. ", port=443, scheme=" HTTPS ")

    assert svc_key == "api.example.com:443/https"
    assert endpoint_key_fn(
        service_key=svc_key,
        method="get",
        normalized_path="/v1/users/{id}",
    ) == "api.example.com:443/https:GET:/v1/users/{id}"


def test_http_observation_dedupe_key_is_stable_for_raw_artifact_and_parser_version() -> None:
    _, dedupe_key, _, _ = _symbols()
    raw_artifact_id = uuid4()

    assert dedupe_key(raw_artifact_id, "http-observations.v1") == (
        f"http-observations:{raw_artifact_id}:http-observations.v1"
    )


def test_http_observation_producer_canonicalizes_hostnames_and_ip_addresses() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()
    row = _observation_row(
        hostname=" API.Example.COM.. ",
        ip_address=" 2001:0db8:0000:0000:0000:0000:0000:0001 ",
    )

    batch = HttpObservationGraphFactProducer().produce([row])

    assert batch is not None
    node_facts = {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}
    assert ("Host", "api.example.com") in node_facts
    assert ("IP", "2001:db8::1") in node_facts
    edge_facts = {
        (fact.src_kind, fact.src_key, fact.edge_kind, fact.dst_kind, fact.dst_key)
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }
    assert ("Host", "api.example.com", "RESOLVES_TO", "IP", "2001:db8::1") in edge_facts
