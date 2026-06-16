from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def _graph_batch_store_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import deserialize_graph_fact_batch, serialize_graph_fact_batch
    from graph_projector.contracts import GraphFactBatch, GraphNodeFact

    return GraphNodeFact, GraphFactBatch, serialize_graph_fact_batch, deserialize_graph_fact_batch


def test_graph_fact_batches_table_is_declared_as_durable_projector_queue() -> None:
    source = Path("src/api/infrastructure/adapters/orm.py").read_text(encoding="utf-8")

    assert "graph_fact_batches = Table(" in source
    assert "'graph_fact_batches'" in source
    for column in [
        "'program_id'",
        "'produced_by'",
        "'parser_version'",
        "'facts_json'",
        "'fact_count'",
        "'status'",
        "'attempts'",
        "'available_at'",
        "'locked_by'",
        "'locked_until'",
        "'created_at'",
        "'updated_at'",
        "'applied_at'",
        "'last_error'",
    ]:
        assert column in source

    assert "ck_graph_fact_batches_status_valid" in source
    assert "ck_graph_fact_batches_attempts_nonnegative" in source
    assert "ck_graph_fact_batches_fact_count_positive" in source
    assert "idx_graph_fact_batches_status_available" in source
    assert "idx_graph_fact_batches_program_created" in source


def test_graph_fact_batch_migration_creates_store_without_neo4j_coupling() -> None:
    migration = Path("alembic/versions/z6a7b8c9d0e1_add_graph_fact_batches.py")
    source = migration.read_text(encoding="utf-8")

    assert "graph_fact_batches" in source
    assert 'down_revision = "y5z6a7b8c9d0"' in source
    assert "postgresql.JSONB" in source
    assert "ck_graph_fact_batches_status_valid" in source
    assert "idx_graph_fact_batches_status_available" in source
    assert "neo4j" not in source.lower()


def test_graph_fact_batch_store_round_trips_contract_without_computed_fields() -> None:
    GraphNodeFact, GraphFactBatch, serialize_graph_fact_batch, deserialize_graph_fact_batch = (
        _graph_batch_store_symbols()
    )

    program_id = uuid4()
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="dnsx-parser",
        parser_version="1.0.0",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="Host",
                key="api.example.com",
                producer="dnsx",
                source_artifact_id=uuid4(),
                tool_run_id=uuid4(),
                confidence=0.95,
            )
        ],
    )

    payload = serialize_graph_fact_batch(batch)

    assert payload["program_id"] == str(program_id)
    assert payload["produced_by"] == "dnsx-parser"
    assert payload["parser_version"] == "1.0.0"
    assert payload["fact_count"] == 1
    assert "identity_key" not in payload["facts_json"]["facts"][0]
    assert deserialize_graph_fact_batch(payload["facts_json"]) == batch


def test_graph_fact_batch_store_has_dedupe_key_for_idempotent_producer_enqueue() -> None:
    orm_source = Path("src/api/infrastructure/adapters/orm.py").read_text(encoding="utf-8")
    migration = Path("alembic/versions/a7b8c9d0e1f2_add_graph_fact_batch_dedupe_key.py")

    assert "'dedupe_key'" in orm_source
    assert "uq_graph_fact_batches_dedupe_key" in orm_source
    assert migration.exists()
    migration_source = migration.read_text(encoding="utf-8")
    assert "dedupe_key" in migration_source
    assert "uq_graph_fact_batches_dedupe_key" in migration_source


def test_graph_fact_batches_notification_migration_notifies_pending_batches() -> None:
    migration = Path("alembic/versions/c9d0e1f2g3h4_add_graph_fact_batch_notifications.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "b8c9d0e1f2g3"' in source
    assert "notify_graph_fact_batch_changed" in source
    assert "CREATE TRIGGER graph_fact_batches_notify_insert" in source
    assert "AFTER INSERT ON graph_fact_batches" in source
    assert "CREATE TRIGGER graph_fact_batches_notify_status" in source
    assert "AFTER UPDATE OF status, available_at ON graph_fact_batches" in source
    assert "pg_notify('graph_fact_batches_changed'" in source
    assert "NEW.status IN ('pending', 'failed')" in source


def test_batch_store_enqueue_can_use_dedupe_key_for_idempotent_inserts() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import GraphFactBatchStore

    GraphNodeFact, GraphFactBatch, _, _ = _graph_batch_store_symbols()
    program_id = uuid4()
    batch = GraphFactBatch(
        program_id=program_id,
        produced_by="raw-artifact-metadata",
        parser_version="raw-artifact-metadata.v1",
        facts=[
            GraphNodeFact(
                program_id=program_id,
                kind="Artifact",
                key=str(uuid4()),
                producer="raw-artifact-metadata",
                source_artifact_id=uuid4(),
                tool_run_id=uuid4(),
                confidence=1.0,
            )
        ],
    )

    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, query, parameters=None):
            self.calls.append((query, parameters or {}))

        def fetchone(self):
            return {"id": uuid4()}

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()
            self.commits = 0

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.commits += 1

        def rollback(self):
            raise AssertionError("enqueue should not rollback")

    connection = Connection()
    store = GraphFactBatchStore(connection)

    store.enqueue(batch, dedupe_key="raw-artifact-metadata:artifact-1:raw-artifact-metadata.v1")

    query, parameters = connection.cursor_obj.calls[0]
    assert "dedupe_key" in query
    assert "ON CONFLICT (dedupe_key)" in query
    assert parameters["dedupe_key"] == "raw-artifact-metadata:artifact-1:raw-artifact-metadata.v1"
    assert connection.commits == 1


def test_batch_store_adapts_graph_fact_json_for_psycopg2_cursor() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import _adapt_json_parameters_for_cursor

    class Psycopg2LikeCursor:
        pass

    Psycopg2LikeCursor.__module__ = "psycopg2.extras"

    payload = {"facts_json": {"facts": []}, "program_id": "program-1"}
    adapted = _adapt_json_parameters_for_cursor(Psycopg2LikeCursor(), payload)

    assert adapted is not payload
    assert getattr(adapted["facts_json"], "adapted") == {"facts": []}
    assert adapted["program_id"] == "program-1"


def test_batch_store_leaves_graph_fact_json_unwrapped_for_non_psycopg2_cursor() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.batch_store import _adapt_json_parameters_for_cursor

    class RecordingCursor:
        pass

    payload = {"facts_json": {"facts": []}, "program_id": "program-1"}
    adapted = _adapt_json_parameters_for_cursor(RecordingCursor(), payload)

    assert adapted is payload
    assert adapted["facts_json"] == {"facts": []}
