from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.contracts import IngestContext
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.created_savepoints: list[str] = []
        self.released_savepoints: list[str] = []
        self.rolled_back_savepoints: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def create_savepoint(self, name: str) -> None:
        self.created_savepoints.append(name)

    async def release_savepoint(self, name: str) -> None:
        self.released_savepoints.append(name)

    async def rollback_to_savepoint(self, name: str) -> None:
        self.rolled_back_savepoints.append(name)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RecordingIngestor(BaseResultIngestor):
    def __init__(self, uow: FakeUnitOfWork) -> None:
        super().__init__(uow, batch_size=1)
        self.before_context: IngestContext | None = None
        self.record_contexts: list[IngestContext | None] = []
        self.records: list[dict[str, object]] = []
        self.build_result_calls = 0
        self.log_extra_calls = 0

    async def before_ingest(
        self,
        uow,
        program_id,
        results,
        context: IngestContext | None = None,
    ) -> None:
        self.before_context = context

    async def process_record(
        self,
        uow,
        program_id,
        record,
        context: IngestContext | None = None,
    ) -> None:
        self.record_contexts.append(context)
        if record.get("boom"):
            raise ValueError("bad record")
        self.records.append(record)

    def build_result(self) -> IngestResult:
        self.build_result_calls += 1
        return IngestResult(raw_domains=[str(record["host"]) for record in self.records])

    def log_extra(self) -> str:
        self.log_extra_calls += 1
        return f"records={len(self.records)}"


@pytest.mark.asyncio
async def test_base_ingestor_handles_savepoints_context_and_result_once() -> None:
    uow = FakeUnitOfWork()
    ingestor = RecordingIngestor(uow)
    context = IngestContext(run_id=uuid4(), raw_artifact_id=uuid4())

    result = await ingestor.ingest(
        uuid4(),
        [
            {"host": "ok.example"},
            {"host": "bad.example", "boom": True},
            {"host": "later.example"},
        ],
        context=context,
    )

    assert result.raw_domains == ["ok.example", "later.example"]
    assert ingestor.before_context is context
    assert ingestor.record_contexts == [context, context, context]
    assert ingestor.build_result_calls == 1
    assert ingestor.log_extra_calls == 1
    assert uow.created_savepoints == ["batch_0", "batch_1", "batch_2"]
    assert uow.released_savepoints == ["batch_0", "batch_2"]
    assert uow.rolled_back_savepoints == ["batch_1"]
    assert uow.commits == 1
    assert uow.rollbacks == 0


def test_base_ingestor_requires_batch_or_record_hook() -> None:
    with pytest.raises(TypeError, match="must implement _process_batch or process_record"):
        class BrokenIngestor(BaseResultIngestor):
            pass
