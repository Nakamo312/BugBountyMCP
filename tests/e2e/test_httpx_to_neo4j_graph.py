from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.e2e


def _graph_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.applicator import GraphFactBatchApplicator
    from graph_projector.batch_store import GraphFactBatchStore, connect_postgres
    from graph_projector.ontology import default_graph_ontology
    from graph_projector.producers.http_observations import HttpObservationGraphFactEnqueuer
    from graph_projector.writer import GraphFactWriter, GraphOntologyRegistry

    return (
        GraphFactBatchApplicator,
        GraphFactBatchStore,
        HttpObservationGraphFactEnqueuer,
        GraphFactWriter,
        GraphOntologyRegistry,
        default_graph_ontology,
        connect_postgres,
    )


def test_fake_httpx_canonical_observation_projects_endpoint_graph(
    e2e_postgres_engine,
    e2e_postgres_url: str,
    e2e_neo4j_driver,
    e2e_neo4j_database: str,
) -> None:
    (
        GraphFactBatchApplicator,
        GraphFactBatchStore,
        HttpObservationGraphFactEnqueuer,
        GraphFactWriter,
        GraphOntologyRegistry,
        default_graph_ontology,
        connect_postgres,
    ) = _graph_symbols()

    program_id = uuid4()
    action_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    raw_artifact_id = uuid4()
    host_id = uuid4()
    ip_id = uuid4()
    host_ip_id = uuid4()
    service_id = uuid4()
    endpoint_id = uuid4()
    observation_id = uuid4()
    correlation_id = uuid4()
    event_dedupe_key = f"http-observations-ready:{raw_artifact_id}"

    with e2e_postgres_engine.begin() as connection:
        _clear_projection_tables(connection)
        _insert_canonical_http_observation(
            connection,
            program_id=program_id,
            action_id=action_id,
            job_id=job_id,
            run_id=run_id,
            raw_artifact_id=raw_artifact_id,
            host_id=host_id,
            ip_id=ip_id,
            host_ip_id=host_ip_id,
            service_id=service_id,
            endpoint_id=endpoint_id,
            observation_id=observation_id,
            correlation_id=correlation_id,
            event_dedupe_key=event_dedupe_key,
        )

    dbapi_url = e2e_postgres_url.replace("postgresql+psycopg2://", "postgresql://")
    pg_connection = connect_postgres(dbapi_url)
    try:
        store = GraphFactBatchStore(pg_connection)
        enqueuer = HttpObservationGraphFactEnqueuer(
            connection=pg_connection,
            store=store,
            worker_id="e2e-http-observations",
        )

        enqueue_result = enqueuer.enqueue_pending(limit=10, program_id=program_id)
        assert enqueue_result.scanned == 1
        assert enqueue_result.enqueued == 1
        assert enqueue_result.skipped == 0
        assert enqueuer.enqueue_pending(limit=10, program_id=program_id).scanned == 0

        applicator = GraphFactBatchApplicator(
            store=store,
            neo4j_driver=e2e_neo4j_driver,
            writer=GraphFactWriter(GraphOntologyRegistry(default_graph_ontology())),
            neo4j_database=e2e_neo4j_database,
            worker_id="e2e-http-observations-applicator",
            lock_seconds=300,
            max_attempts=3,
        )
        apply_result = applicator.apply_one()
        assert apply_result.status == "applied"
        assert apply_result.write_result is not None
        assert apply_result.write_result.edges_skipped == 0
        assert applicator.apply_one().status == "empty"
    finally:
        pg_connection.close()

    with e2e_neo4j_driver.session(database=e2e_neo4j_database) as session:
        counts = session.run(
            """
            MATCH (h:Host {hostname: 'api.example.com'})-[:RESOLVES_TO]->(ip:IP {address: '203.0.113.10'})
            MATCH (ip)-[:EXPOSES_SERVICE]->(s:Service {service_key: 'api.example.com:443/https'})
            MATCH (s)-[:HAS_ENDPOINT]->(e:Endpoint {service_method_normalized_path: 'api.example.com:443/https:GET:/v1/users/{id}'})
            RETURN count(DISTINCT h) AS hosts,
                   count(DISTINCT ip) AS ips,
                   count(DISTINCT s) AS services,
                   count(DISTINCT e) AS endpoints,
                   count { (h)-[:RESOLVES_TO]->(ip) } AS resolves_to,
                   count { (ip)-[:EXPOSES_SERVICE]->(s) } AS exposes_service,
                   count { (s)-[:HAS_ENDPOINT]->(e) } AS has_endpoint
            """
        ).mappings().one()

    assert counts["hosts"] == 1
    assert counts["ips"] == 1
    assert counts["services"] == 1
    assert counts["endpoints"] == 1
    assert counts["resolves_to"] == 1
    assert counts["exposes_service"] == 1
    assert counts["has_endpoint"] == 1


def _clear_projection_tables(connection) -> None:
    for table in [
        "graph_fact_batches",
        "graph_projection_events",
        "http_observation_headers",
        "http_observations",
        "raw_artifacts",
        "endpoints",
        "services",
        "host_ips",
        "ip_addresses",
        "hosts",
        "runs",
        "jobs",
        "action_requests",
        "programs",
    ]:
        connection.execute(text(f"DELETE FROM {table}"))


def _insert_canonical_http_observation(
    connection,
    *,
    program_id,
    action_id,
    job_id,
    run_id,
    raw_artifact_id,
    host_id,
    ip_id,
    host_ip_id,
    service_id,
    endpoint_id,
    observation_id,
    correlation_id,
    event_dedupe_key: str,
) -> None:
    connection.execute(
        text("INSERT INTO programs (id, name) VALUES (:id, :name)"),
        {"id": program_id, "name": f"e2e-httpx-graph-{program_id}"},
    )
    connection.execute(
        text(
            """
            INSERT INTO action_requests (
                id, program_id, kind, capability_id, profile_id, requested_by,
                correlation_id, metadata, status, request
            ) VALUES (
                :id, :program_id, 'tool_action', 'httpx', 'default', 'e2e',
                :correlation_id, '{}'::jsonb, 'queued', '{}'::jsonb
            )
            """
        ),
        {"id": action_id, "program_id": program_id, "correlation_id": correlation_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO jobs (
                id, action_id, program_id, capability_id, profile_id, status, correlation_id
            ) VALUES (
                :id, :action_id, :program_id, 'httpx', 'default', 'completed', :correlation_id
            )
            """
        ),
        {
            "id": job_id,
            "action_id": action_id,
            "program_id": program_id,
            "correlation_id": correlation_id,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO runs (
                id, job_id, program_id, node_id, event_name, execution_mode,
                status, attempt, terminal_outcome
            ) VALUES (
                :id, :job_id, :program_id, 'httpx', 'httpx_scan_requested',
                'inline', 'completed', 1, 'completed'
            )
            """
        ),
        {"id": run_id, "job_id": job_id, "program_id": program_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO raw_artifacts (
                id, program_id, job_id, run_id, node_id, event_name, artifact_type,
                storage_uri, sha256, size_bytes, artifact_metadata
            ) VALUES (
                :id, :program_id, :job_id, :run_id, 'httpx', 'httpx.completed',
                'raw_tool_output', 'raw://e2e/httpx.ndjson', :sha256, 123, '{}'::jsonb
            )
            """
        ),
        {
            "id": raw_artifact_id,
            "program_id": program_id,
            "job_id": job_id,
            "run_id": run_id,
            "sha256": "a" * 64,
        },
    )
    connection.execute(
        text(
            "INSERT INTO hosts (id, program_id, host, in_scope, cname) "
            "VALUES (:id, :program_id, 'api.example.com', true, '[]'::jsonb)"
        ),
        {"id": host_id, "program_id": program_id},
    )
    connection.execute(
        text(
            "INSERT INTO ip_addresses (id, program_id, address, in_scope) "
            "VALUES (:id, :program_id, '203.0.113.10', true)"
        ),
        {"id": ip_id, "program_id": program_id},
    )
    connection.execute(
        text(
            "INSERT INTO host_ips (id, host_id, ip_id, source) "
            "VALUES (:id, :host_id, :ip_id, 'httpx')"
        ),
        {"id": host_ip_id, "host_id": host_id, "ip_id": ip_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO services (id, ip_id, scheme, port, technologies, websocket)
            VALUES (:id, :ip_id, 'https', 443, '{}'::jsonb, false)
            """
        ),
        {"id": service_id, "ip_id": ip_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO endpoints (
                id, host_id, service_id, path, normalized_path, methods, status_code
            ) VALUES (
                :id, :host_id, :service_id, '/v1/users/123',
                '/v1/users/{id}', ARRAY['GET'], 200
            )
            """
        ),
        {"id": endpoint_id, "host_id": host_id, "service_id": service_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO http_observations (
                id, program_id, endpoint_id, service_id, job_id, run_id,
                raw_artifact_id, method, url, status_code, content_type,
                source_tool, metadata
            ) VALUES (
                :id, :program_id, :endpoint_id, :service_id, :job_id, :run_id,
                :raw_artifact_id, 'GET', 'https://api.example.com/v1/users/123',
                200, 'application/json', 'httpx', '{}'::jsonb
            )
            """
        ),
        {
            "id": observation_id,
            "program_id": program_id,
            "endpoint_id": endpoint_id,
            "service_id": service_id,
            "job_id": job_id,
            "run_id": run_id,
            "raw_artifact_id": raw_artifact_id,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO graph_projection_events (
                program_id, source_type, source_id, event_type, dedupe_key
            ) VALUES (
                :program_id, 'raw_artifact', :source_id,
                'http_observations_ready', :dedupe_key
            )
            ON CONFLICT (dedupe_key) DO NOTHING
            """
        ),
        {
            "program_id": program_id,
            "source_id": raw_artifact_id,
            "dedupe_key": event_dedupe_key,
        },
    )
