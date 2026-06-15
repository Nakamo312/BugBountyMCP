from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


def _graph_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import GraphFactBatchStore, connect_postgres
    from graph_projector.producers.http_observations import HttpObservationGraphFactEnqueuer

    return connect_postgres, GraphFactBatchStore, HttpObservationGraphFactEnqueuer


def test_http_observation_ready_event_can_be_inserted_and_claimed(
    integration_postgres_sync_url: str,
    integration_sync_engine,
) -> None:
    connect_postgres, GraphFactBatchStore, HttpObservationGraphFactEnqueuer = _graph_symbols()
    program_id = uuid4()
    raw_artifact_id = uuid4()
    projection_event_id = uuid4()
    dedupe_key = f"http-observations-ready:{raw_artifact_id}"

    with integration_sync_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO programs (id, name) VALUES (:id, :name)"),
            {"id": program_id, "name": f"integration-http-events-{raw_artifact_id}"},
        )
        connection.execute(
            text(
                """
                INSERT INTO graph_projection_events (
                    id, program_id, source_type, source_id, event_type, dedupe_key
                ) VALUES (
                    :id, :program_id, 'raw_artifact', :source_id,
                    'http_observations_ready', :dedupe_key
                )
                ON CONFLICT (dedupe_key) DO NOTHING
                """
            ),
            {
                "id": projection_event_id,
                "program_id": program_id,
                "source_id": raw_artifact_id,
                "dedupe_key": dedupe_key,
            },
        )

    dbapi_url = integration_postgres_sync_url.replace("postgresql+psycopg2://", "postgresql://")
    pg_connection = connect_postgres(dbapi_url)
    try:
        enqueuer = HttpObservationGraphFactEnqueuer(
            connection=pg_connection,
            store=GraphFactBatchStore(pg_connection),
            worker_id="integration-http-observations",
        )

        result = enqueuer.enqueue_pending(limit=10, program_id=program_id)
    finally:
        pg_connection.close()

    assert result.scanned == 1
    assert result.enqueued == 0
    assert result.skipped == 1

    with integration_sync_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT source_type, event_type, status, processed_at
                FROM graph_projection_events
                WHERE dedupe_key = :dedupe_key
                """
            ),
            {"dedupe_key": dedupe_key},
        ).mappings().one()

    assert row["source_type"] == "raw_artifact"
    assert row["event_type"] == "http_observations_ready"
    assert row["status"] == "processed"
    assert row["processed_at"] is not None
