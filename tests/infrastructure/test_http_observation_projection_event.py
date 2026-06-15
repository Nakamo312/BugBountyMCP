from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from api.domain.models import HTTPObservationHeaderModel, HTTPObservationModel
from api.infrastructure.repositories.adapters.http_observation import (
    SQLAlchemyHTTPObservationRepository,
)


class FakeAsyncSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.executed: list[object] = []
        self.flushes = 0

    def add(self, entity: object) -> None:
        self.added.append(entity)

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def flush(self) -> None:
        self.flushes += 1


def _observation(**overrides: object) -> HTTPObservationModel:
    values = {
        "program_id": uuid4(),
        "endpoint_id": uuid4(),
        "service_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
        "raw_artifact_id": uuid4(),
        "method": "GET",
        "url": "https://api.example.com/",
        "source_tool": "httpx",
    }
    values.update(overrides)
    return HTTPObservationModel(**values)


@pytest.mark.asyncio
async def test_http_observation_repository_enqueues_ready_projection_event() -> None:
    session = FakeAsyncSession()
    repository = SQLAlchemyHTTPObservationRepository(session)
    observation = _observation()

    await repository.create_with_headers(
        observation,
        headers=[
            {"name": "server", "value": "nginx"},
            {"name": "content-type", "value": "text/html"},
        ],
    )

    assert session.added[0] is observation
    assert len(session.added) == 3
    header_models = session.added[1:]
    assert all(isinstance(header, HTTPObservationHeaderModel) for header in header_models)
    assert [
        (header.observation_id, header.name, header.value, header.ordinal)
        for header in header_models
    ] == [
        (observation.id, "server", "nginx", 0),
        (observation.id, "content-type", "text/html", 1),
    ]
    assert len(session.executed) == 1
    compiled = session.executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = compiled.params

    assert "INSERT INTO graph_projection_events" in sql
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in sql
    assert params["program_id"] == observation.program_id
    assert params["source_type"] == "raw_artifact"
    assert params["source_id"] == observation.raw_artifact_id
    assert params["event_type"] == "http_observations_ready"
    assert params["dedupe_key"] == f"http-observations-ready:{observation.raw_artifact_id}"


@pytest.mark.asyncio
async def test_http_observation_repository_skips_projection_event_without_lineage() -> None:
    for observation in [
        _observation(raw_artifact_id=None),
        _observation(run_id=None),
    ]:
        session = FakeAsyncSession()
        repository = SQLAlchemyHTTPObservationRepository(session)

        await repository.create_with_headers(observation)

        assert session.executed == []
