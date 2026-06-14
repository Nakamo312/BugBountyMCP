from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4


def _apply_symbols():
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.applicator import GraphFactBatchApplicator
    from graph_projector.batch_store import ClaimedGraphFactBatch, GraphFactBatchStore
    from graph_projector.contracts import GraphFactBatch, GraphNodeFact
    from graph_projector.ontology import default_graph_ontology
    from graph_projector.writer import GraphFactWriter, GraphOntologyRegistry

    return (
        GraphFactBatchApplicator,
        ClaimedGraphFactBatch,
        GraphFactBatchStore,
        GraphFactBatch,
        GraphNodeFact,
        default_graph_ontology,
        GraphFactWriter,
        GraphOntologyRegistry,
    )


@dataclass
class StoreCall:
    name: str
    args: tuple[object, ...]


class FakeBatchStore:
    def __init__(self, claimed) -> None:
        self.claimed = claimed
        self.calls: list[StoreCall] = []

    def claim_next(self, *, worker_id: str, lock_seconds: int, max_attempts: int):
        self.calls.append(StoreCall("claim_next", (worker_id, lock_seconds, max_attempts)))
        return self.claimed

    def mark_applied(self, batch_id: UUID) -> None:
        self.calls.append(StoreCall("mark_applied", (batch_id,)))

    def mark_failed(self, batch_id: UUID, *, error: str, dead: bool) -> None:
        self.calls.append(StoreCall("mark_failed", (batch_id, error, dead)))


class SequenceBatchStore:
    def __init__(self, claimed_batches) -> None:
        self.claimed_batches = list(claimed_batches)
        self.calls: list[StoreCall] = []

    def claim_next(self, *, worker_id: str, lock_seconds: int, max_attempts: int):
        self.calls.append(StoreCall("claim_next", (worker_id, lock_seconds, max_attempts)))
        if not self.claimed_batches:
            return None
        return self.claimed_batches.pop(0)

    def mark_applied(self, batch_id: UUID) -> None:
        self.calls.append(StoreCall("mark_applied", (batch_id,)))

    def mark_failed(self, batch_id: UUID, *, error: str, dead: bool) -> None:
        self.calls.append(StoreCall("mark_failed", (batch_id, error, dead)))


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def run(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append((query, parameters or {}))
        return []


class FakeDriver:
    def __init__(self) -> None:
        self.session_obj = FakeSession()
        self.databases: list[str] = []

    def session(self, *, database: str):
        self.databases.append(database)
        return self.session_obj


class FailingDriver:
    def session(self, *, database: str):
        raise RuntimeError(f"cannot connect to {database}")


def _claimed_batch():
    (
        _,
        ClaimedGraphFactBatch,
        _,
        GraphFactBatch,
        GraphNodeFact,
        _,
        _,
        _,
    ) = _apply_symbols()

    program_id = uuid4()
    artifact_id = uuid4()
    tool_run_id = uuid4()
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
                source_artifact_id=artifact_id,
                tool_run_id=tool_run_id,
                confidence=0.95,
            )
        ],
    )
    return ClaimedGraphFactBatch(batch_id=uuid4(), batch=batch, attempts=1)


def test_batch_store_claim_sql_uses_skip_locked_and_deserializes_batch() -> None:
    _, ClaimedGraphFactBatch, GraphFactBatchStore, *_ = _apply_symbols()

    source = Path("services/graph-projector/graph_projector/batch_store.py").read_text(encoding="utf-8")

    assert "class GraphFactBatchStore" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "status IN ('pending', 'failed')" in source
    assert "RETURNING" in source
    assert "deserialize_graph_fact_batch" in source
    assert ClaimedGraphFactBatch.__annotations__["batch"]
    assert GraphFactBatchStore


def test_applicator_applies_one_claimed_batch_and_marks_applied() -> None:
    GraphFactBatchApplicator, _, _, _, _, default_graph_ontology, GraphFactWriter, GraphOntologyRegistry = (
        _apply_symbols()
    )

    claimed = _claimed_batch()
    store = FakeBatchStore(claimed)
    driver = FakeDriver()
    writer = GraphFactWriter(GraphOntologyRegistry(default_graph_ontology()))
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=driver,
        writer=writer,
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_one()

    assert result.status == "applied"
    assert result.batch_id == claimed.batch_id
    assert result.write_result.nodes_written == 1
    assert driver.databases == ["neo4j"]
    assert [call.name for call in store.calls] == ["claim_next", "mark_applied"]


def test_applicator_marks_failed_batch_dead_after_final_attempt() -> None:
    GraphFactBatchApplicator, *_ = _apply_symbols()

    claimed = _claimed_batch()
    claimed = type(claimed)(batch_id=claimed.batch_id, batch=claimed.batch, attempts=3)
    store = FakeBatchStore(claimed)
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=FailingDriver(),
        writer=object(),
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_one()

    assert result.status == "dead"
    assert result.batch_id == claimed.batch_id
    assert store.calls[-1].name == "mark_failed"
    assert store.calls[-1].args[2] is True


def test_graph_projector_settings_parse_postgres_connection(monkeypatch) -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.settings import GraphProjectorSettings

    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "bugbounty")
    monkeypatch.setenv("POSTGRES_USER", "bb")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("GRAPH_PROJECTOR_WORKER_ID", "graph-worker-a")
    monkeypatch.setenv("GRAPH_FACT_BATCH_LOCK_SECONDS", "120")
    monkeypatch.setenv("GRAPH_FACT_BATCH_MAX_ATTEMPTS", "5")

    settings = GraphProjectorSettings.from_env()

    assert settings.postgres_dsn == "postgresql://bb:secret@postgres:5432/bugbounty"
    assert settings.worker_id == "graph-worker-a"
    assert settings.batch_lock_seconds == 120
    assert settings.batch_max_attempts == 5


def test_apply_one_cli_command_is_exposed_without_producer_loop() -> None:
    source = Path("services/graph-projector/graph_projector/__main__.py").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("apply-one"' in source
    assert "GraphFactBatchApplicator" in source
    assert "while True" not in source


def test_applicator_loop_applies_batches_until_empty_threshold() -> None:
    GraphFactBatchApplicator, _, _, _, _, default_graph_ontology, GraphFactWriter, GraphOntologyRegistry = (
        _apply_symbols()
    )

    first = _claimed_batch()
    second = _claimed_batch()
    store = SequenceBatchStore([first, second])
    driver = FakeDriver()
    writer = GraphFactWriter(GraphOntologyRegistry(default_graph_ontology()))
    slept: list[float] = []
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=driver,
        writer=writer,
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_loop(
        max_batches=10,
        idle_exit_after=1,
        poll_seconds=0.25,
        sleep=slept.append,
    )

    assert result.applied == 2
    assert result.failed == 0
    assert result.dead == 0
    assert result.empty == 1
    assert result.iterations == 3
    assert result.last_status == "empty"
    assert [call.name for call in store.calls].count("mark_applied") == 2
    assert slept == []


def test_applicator_loop_sleeps_between_empty_polls_when_not_exiting() -> None:
    GraphFactBatchApplicator, *_ = _apply_symbols()

    store = SequenceBatchStore([])
    slept: list[float] = []
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=FakeDriver(),
        writer=object(),
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_loop(
        max_batches=2,
        idle_exit_after=None,
        poll_seconds=0.5,
        sleep=slept.append,
    )

    assert result.applied == 0
    assert result.empty == 2
    assert result.iterations == 2
    assert slept == [0.5, 0.5]


def test_applicator_loop_waits_for_graphfact_batch_notifications_between_empty_polls() -> None:
    GraphFactBatchApplicator, *_ = _apply_symbols()

    store = SequenceBatchStore([])
    slept: list[float] = []
    waits: list[float] = []
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=FakeDriver(),
        writer=object(),
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_loop(
        max_batches=2,
        idle_exit_after=None,
        poll_seconds=0.75,
        sleep=slept.append,
        wait_for_notification=waits.append,
    )

    assert result.empty == 2
    assert result.iterations == 2
    assert waits == [0.75, 0.75]
    assert slept == []


def test_graph_projector_settings_parse_apply_loop_controls(monkeypatch) -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.settings import GraphProjectorSettings

    monkeypatch.setenv("GRAPH_FACT_BATCH_POLL_SECONDS", "1.5")
    monkeypatch.setenv("GRAPH_FACT_BATCH_NOTIFY_CHANNEL", "graph_fact_batches_changed_test")

    settings = GraphProjectorSettings.from_env()

    assert settings.batch_poll_seconds == 1.5
    assert settings.graph_fact_batch_notify_channel == "graph_fact_batches_changed_test"


def test_graphfact_batch_notification_waiter_listens_to_configured_channel() -> None:
    source = Path("services/graph-projector/graph_projector/applicator.py").read_text(encoding="utf-8")

    assert "class GraphFactBatchNotificationWaiter" in source
    assert "LISTEN" in source
    assert "graph_fact_batches_changed" in source


def test_apply_loop_cli_command_is_exposed_without_producers() -> None:
    source = Path("services/graph-projector/graph_projector/__main__.py").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("apply-loop"' in source
    assert "apply_loop" in source
    assert "RawArtifactGraphFactProducer" in source
    assert "enqueue-raw-artifacts" in source


def test_graph_projector_compose_runs_apply_loop_by_default() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "graph-projector:" in compose
    assert 'command: ["apply-loop"]' in compose
    assert "GRAPH_FACT_BATCH_POLL_SECONDS" in compose
    assert "GRAPH_FACT_BATCH_NOTIFY_CHANNEL" in compose


def test_applicator_retries_batch_when_writer_skips_edges() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.applicator import GraphFactBatchApplicator
    from graph_projector.writer import GraphFactWriteResult

    class SkippingWriter:
        def write_batch(self, session, batch):
            return GraphFactWriteResult(nodes_written=0, edges_written=0, edges_skipped=1)

    claimed = _claimed_batch()
    store = FakeBatchStore(claimed)
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=FakeDriver(),
        writer=SkippingWriter(),
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_one()

    assert result.status == "failed"
    assert result.batch_id == claimed.batch_id
    assert result.write_result is not None
    assert result.write_result.edges_skipped == 1
    assert [call.name for call in store.calls] == ["claim_next", "mark_failed"]
    assert store.calls[-1].args[1] == "GraphFactBatch skipped 1 edge(s); missing endpoint nodes may arrive later"
    assert store.calls[-1].args[2] is False


def test_applicator_marks_skipped_edge_batch_dead_after_final_attempt() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.applicator import GraphFactBatchApplicator
    from graph_projector.writer import GraphFactWriteResult

    class SkippingWriter:
        def write_batch(self, session, batch):
            return GraphFactWriteResult(nodes_written=0, edges_written=0, edges_skipped=2)

    claimed = _claimed_batch()
    claimed = type(claimed)(batch_id=claimed.batch_id, batch=claimed.batch, attempts=3)
    store = FakeBatchStore(claimed)
    applicator = GraphFactBatchApplicator(
        store=store,
        neo4j_driver=FakeDriver(),
        writer=SkippingWriter(),
        neo4j_database="neo4j",
        worker_id="worker-1",
        lock_seconds=60,
        max_attempts=3,
    )

    result = applicator.apply_one()

    assert result.status == "dead"
    assert result.batch_id == claimed.batch_id
    assert store.calls[-1].name == "mark_failed"
    assert store.calls[-1].args[1] == "GraphFactBatch skipped 2 edge(s); missing endpoint nodes may arrive later"
    assert store.calls[-1].args[2] is True
