from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer import projection_state  # noqa: E402
from search_indexer.projection_state import ProjectionRun, ProjectionStateStore  # noqa: E402
from search_indexer.reindex import reindex_target  # noqa: E402


class FakeReader:
    def __init__(self, rows):
        self.rows = rows
        self.fetch_calls = []
        self.count_calls = []

    def count_target(self, *, target, program_id, filters=None):
        self.count_calls.append((target, program_id, filters or {}))
        return len(self.rows)

    def fetch_http_observations(self, *, limit, offset=0, program_id=None):
        self.fetch_calls.append((limit, offset, program_id))
        return self.rows[offset : offset + limit]


class FakeClient:
    def ensure_ism_policy(self, *args):
        return None

    def ensure_index(self, *args):
        return None

    def apply_ism_policy(self, *args):
        return None

    def bulk_index(self, index_name, documents):
        return {"errors": False, "items": list(documents)}


class FakeProjectionStore:
    def __init__(self):
        self.started = []
        self.completed = []
        self.failed = []

    def start(self, *, program_id, projection_name, total_count):
        self.started.append((program_id, projection_name, total_count))
        return ProjectionRun(program_id, projection_name, "watermark-1", total_count)

    def complete(self, run, *, indexed_count):
        self.completed.append((run, indexed_count))
        return indexed_count >= run.total_count

    def fail(self, run, *, error):
        self.failed.append((run, error))


def test_program_scoped_reindex_tracks_projection_snapshot() -> None:
    reader = FakeReader([{"id": "1", "program_id": "program-1"}])
    state_store = FakeProjectionStore()

    indexed = reindex_target(
        target="http-observations",
        reader=reader,
        client=FakeClient(),
        limit=100,
        batch_size=50,
        program_id="program-1",
        projection_state_store=state_store,
    )

    assert indexed == 1
    assert reader.count_calls == [("http-observations", "program-1", {})]
    assert reader.fetch_calls == [(50, 0, "program-1")]
    assert state_store.started == [("program-1", "http-observations", 1)]
    assert state_store.completed[0][1] == 1
    assert state_store.failed == []


def test_program_scoped_reindex_records_failure_before_reraising() -> None:
    reader = FakeReader([{"id": "1", "program_id": "program-1"}])
    state_store = FakeProjectionStore()

    class FailingClient(FakeClient):
        def bulk_index(self, index_name, documents):
            raise RuntimeError("bulk failed")

    try:
        reindex_target(
            target="http-observations",
            reader=reader,
            client=FailingClient(),
            limit=100,
            batch_size=50,
            program_id="program-1",
            projection_state_store=state_store,
        )
    except RuntimeError as exc:
        assert str(exc) == "bulk failed"
    else:
        raise AssertionError("expected bulk failure")

    assert state_store.completed == []
    assert state_store.failed[0][1] == "bulk failed"


class RecordingCursor:
    def __init__(self, *, source_watermark="watermark-1", rowcount=1):
        self.source_watermark = source_watermark
        self.rowcount = rowcount
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return {"source_watermark": self.source_watermark}


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self, **kwargs):
        return self._cursor


def test_projection_state_store_completes_only_the_started_watermark(monkeypatch) -> None:
    cursor = RecordingCursor(source_watermark="watermark-1", rowcount=1)
    monkeypatch.setattr(
        projection_state.psycopg2,
        "connect",
        lambda dsn: RecordingConnection(cursor),
    )
    store = ProjectionStateStore("postgresql://test")

    run = store.start(
        program_id="program-1",
        projection_name="http-observations",
        total_count=4,
    )
    completed = store.complete(run, indexed_count=4)

    assert completed is True
    assert run.source_watermark == "watermark-1"
    complete_sql, complete_params = cursor.calls[-1]
    assert "source_watermark = %s" in complete_sql
    assert complete_params[-1] == "watermark-1"


def test_projection_state_store_keeps_partial_reindex_lagging(monkeypatch) -> None:
    cursor = RecordingCursor()
    monkeypatch.setattr(
        projection_state.psycopg2,
        "connect",
        lambda dsn: RecordingConnection(cursor),
    )
    store = ProjectionStateStore("postgresql://test")
    run = ProjectionRun("program-1", "http-observations", "watermark-1", 10)

    completed = store.complete(run, indexed_count=3)

    assert completed is False
    sql, params = cursor.calls[-1]
    assert "status = 'observed'" in sql
    assert params[0] == 7


def test_projection_state_store_uses_static_watermark_statements() -> None:
    source = Path("services/search-indexer/search_indexer/projection_state.py").read_text(encoding="utf-8")

    assert "_INSERT_PROJECTION_WATERMARK_BOOTSTRAP" in source
    assert "_MARK_PROJECTION_WATERMARK_RUNNING" in source
    assert "_MARK_PROJECTION_WATERMARK_READY" in source
    assert "_MARK_PROJECTION_WATERMARK_FAILED" in source
    assert "cursor.execute(\n                    \"\"\"" not in source


def test_projection_state_store_rejects_negative_counts() -> None:
    store = ProjectionStateStore("postgresql://test")

    try:
        store.start(program_id="program-1", projection_name="http-observations", total_count=-1)
    except ValueError as exc:
        assert "total_count" in str(exc)
    else:
        raise AssertionError("expected negative total_count to be rejected")

    run = ProjectionRun("program-1", "http-observations", "watermark-1", 10)
    try:
        store.complete(run, indexed_count=-1)
    except ValueError as exc:
        assert "indexed_count" in str(exc)
    else:
        raise AssertionError("expected negative indexed_count to be rejected")
