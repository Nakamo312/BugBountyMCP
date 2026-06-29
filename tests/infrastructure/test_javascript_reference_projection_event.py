from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from api.domain.models import JavaScriptReferenceModel
from api.infrastructure.repositories.adapters.javascript_reference import (
    SQLAlchemyJavaScriptReferenceRepository,
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


def _reference(**overrides: object) -> JavaScriptReferenceModel:
    values = {
        "program_id": uuid4(),
        "endpoint_id": uuid4(),
        "service_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
        "raw_artifact_id": uuid4(),
        "source_tool": "linkfinder",
        "source_url": "https://app.example.com/static/app.js?v=123",
        "referenced_url": "https://api.example.com/v1/users/123?token=secret",
        "reference_type": "endpoint",
    }
    values.update(overrides)
    return JavaScriptReferenceModel(**values)


@pytest.mark.asyncio
async def test_javascript_reference_repository_enqueues_ready_projection_event() -> None:
    session = FakeAsyncSession()
    repository = SQLAlchemyJavaScriptReferenceRepository(session)
    reference = _reference()

    await repository.create(reference)

    assert session.added == [reference]
    assert len(session.executed) == 1
    compiled = session.executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = compiled.params

    assert "INSERT INTO graph_projection_events" in sql
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in sql
    assert params["program_id"] == reference.program_id
    assert params["source_type"] == "raw_artifact"
    assert params["source_id"] == reference.raw_artifact_id
    assert params["event_type"] == "javascript_references_ready"
    assert params["dedupe_key"] == f"javascript-references-ready:{reference.raw_artifact_id}"


@pytest.mark.asyncio
async def test_javascript_reference_repository_skips_projection_event_without_lineage() -> None:
    for reference in [
        _reference(raw_artifact_id=None),
        _reference(run_id=None),
    ]:
        session = FakeAsyncSession()
        repository = SQLAlchemyJavaScriptReferenceRepository(session)

        await repository.create(reference)

        assert session.executed == []
