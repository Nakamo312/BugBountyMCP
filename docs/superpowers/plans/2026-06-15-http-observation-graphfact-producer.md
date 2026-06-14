# HTTP Observation GraphFact Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production GraphFact producer that projects `httpx` canonical HTTP observations into Neo4j `Host`, `IP`, `Service`, and `Endpoint` graph facts.

**Architecture:** Emit a durable `http_observations_ready` projection event after `HTTPXResultIngestor` writes canonical observations for a raw artifact. A standalone graph-projector enqueuer claims those events, builds ontology-compatible GraphFact batches from PostgreSQL joins, and the existing applicator writes them to Neo4j. E2E tests use a deterministic fake `httpx` runner and isolated Postgres/Neo4j services; no real scanner binaries or external probes run.

**Tech Stack:** Python, pytest, SQLAlchemy async/sync, Alembic, PostgreSQL, Neo4j, existing `services/graph-projector` package, Docker Compose integration stack.

---

## File Structure

- Create: `services/graph-projector/graph_projector/producers/http_observations.py`
  - Owns HTTP observation GraphFact production, event claiming, batch enqueue, and loop result aggregation.
- Modify: `services/graph-projector/graph_projector/__main__.py`
  - Adds `enqueue-http-observations` and `enqueue-http-observations-loop` CLI commands.
- Modify: `services/graph-projector/graph_projector/settings.py`
  - Adds HTTP observation enqueue limit and poll interval settings.
- Modify: `src/api/infrastructure/repositories/adapters/http_observation.py`
  - Inserts `http_observations_ready` projection events inside the same transaction as created observations.
- Modify: `src/api/infrastructure/adapters/orm.py`
  - No schema change required; reuse `graph_projection_events`.
- Create: `tests/infrastructure/test_http_observation_graphfact_producer.py`
  - Unit tests for producer keys, facts, event claiming SQL, idempotent dedupe keys, and loop behavior.
- Create: `tests/infrastructure/test_http_observation_projection_event.py`
  - Unit tests for repository-side projection event insertion.
- Modify: `tests/infrastructure/test_graph_projection_events.py`
  - Extends graph projection event contract tests to include `http_observations_ready`.
- Modify: `docker-compose.yml`
  - Adds optional graph profile service for the HTTP observation enqueuer.
- Modify: `pytest.ini`
  - Registers the `e2e` marker.
- Create: `tests/e2e/conftest.py`
  - Provides isolated e2e guards, Postgres URLs, Neo4j driver fixture, and migration setup.
- Create: `tests/e2e/test_httpx_to_neo4j_graph.py`
  - Exercises fake `httpx` output through canonical ingest, GraphFact enqueue/apply, and Neo4j assertions.
- Modify: `docs/testing/integration-tests.md`
  - Documents `RUN_E2E_TESTS=1` and the isolated graph e2e workflow.

---

### Task 1: Producer Unit Test

**Files:**
- Create: `tests/infrastructure/test_http_observation_graphfact_producer.py`
- Create later: `services/graph-projector/graph_projector/producers/http_observations.py`

- [ ] **Step 1: Write the failing producer test**

Create `tests/infrastructure/test_http_observation_graphfact_producer.py` with:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


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

    endpoint_fact = next(fact for fact in batch.facts if getattr(fact, "kind", None) == "Endpoint")
    assert endpoint_fact.properties["service_key"] == svc_key
    assert endpoint_fact.properties["service_method_normalized_path"] == endpoint_key
    assert endpoint_fact.properties["method"] == "GET"
    assert endpoint_fact.properties["normalized_path"] == "/v1/users/{id}"
    assert endpoint_fact.properties["status_code"] == 200
    assert endpoint_fact.properties["content_type"] == "application/json"

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
    identity_keys = [fact.identity_key for fact in batch.facts]
    assert len(identity_keys) == len(set(identity_keys))


def test_http_observation_producer_skips_rows_without_run_or_artifact_lineage() -> None:
    HttpObservationGraphFactProducer, _, _, _ = _symbols()

    assert HttpObservationGraphFactProducer().produce([_observation_row(run_id=None)]) is None
    assert HttpObservationGraphFactProducer().produce([_observation_row(raw_artifact_id=None)]) is None


def test_http_observation_key_helpers_match_ontology_identity_inputs() -> None:
    _, _, service_key_fn, endpoint_key_fn = _symbols()

    svc_key = service_key_fn(hostname="API.Example.COM", port=443, scheme="HTTPS")

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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'graph_projector.producers.http_observations'`.

---

### Task 2: Implement HTTP Observation Producer

**Files:**
- Create: `services/graph-projector/graph_projector/producers/http_observations.py`
- Test: `tests/infrastructure/test_http_observation_graphfact_producer.py`

- [ ] **Step 1: Add producer implementation**

Create `services/graph-projector/graph_projector/producers/http_observations.py` with these public objects:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping, Protocol
from uuid import UUID

from ..batch_store import GraphFactBatchStore
from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .raw_artifacts import default_sleep


class HttpObservationCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class HttpObservationConnection(Protocol):
    def cursor(self) -> HttpObservationCursor: ...


@dataclass(frozen=True)
class HttpObservationEnqueueResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class HttpObservationEnqueueLoopResult:
    scanned: int = 0
    enqueued: int = 0
    skipped: int = 0
    empty: int = 0
    iterations: int = 0

    @staticmethod
    def run(
        enqueuer: Any,
        *,
        limit: int,
        program_id: UUID | str | None = None,
        max_iterations: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
    ) -> "HttpObservationEnqueueLoopResult":
        if limit <= 0:
            raise ValueError("limit must be positive")
        if max_iterations is not None and max_iterations <= 0:
            raise ValueError("max_iterations must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        scanned = enqueued = skipped = empty = iterations = consecutive_empty = 0
        while max_iterations is None or iterations < max_iterations:
            result = enqueuer.enqueue_pending(limit=limit, program_id=program_id)
            iterations += 1
            scanned += result.scanned
            enqueued += result.enqueued
            skipped += result.skipped
            if result.scanned == 0:
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    sleep(poll_seconds)
            else:
                consecutive_empty = 0
        return HttpObservationEnqueueLoopResult(scanned, enqueued, skipped, empty, iterations)


class HttpObservationGraphFactProducer:
    def __init__(self, *, parser_version: str = "http-observations.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        facts = []
        seen: set[str] = set()
        program_id: UUID | None = None

        for row in rows:
            row_program_id = _required_uuid(row, "program_id")
            run_id = _optional_uuid(row.get("run_id"))
            raw_artifact_id = _optional_uuid(row.get("raw_artifact_id"))
            if run_id is None or raw_artifact_id is None:
                continue
            if program_id is None:
                program_id = row_program_id
            elif program_id != row_program_id:
                raise ValueError("http observation batch cannot mix program_id values")

            hostname = _required_text(row, "hostname").lower()
            ip_address = _required_text(row, "ip_address")
            scheme = _required_text(row, "scheme").lower()
            port = int(row.get("port") or 0)
            method = _required_text(row, "method").upper()
            normalized_path = _required_text(row, "normalized_path")
            svc_key = service_key(hostname=hostname, port=port, scheme=scheme)
            endpoint_key = service_method_normalized_path_key(
                service_key=svc_key,
                method=method,
                normalized_path=normalized_path,
            )
            lineage = {
                "program_id": row_program_id,
                "producer": "httpx",
                "source_artifact_id": raw_artifact_id,
                "tool_run_id": run_id,
                "confidence": 1.0,
            }
            candidates = [
                GraphNodeFact(
                    **lineage,
                    kind="Host",
                    key=hostname,
                    properties={"hostname": hostname},
                ),
                GraphNodeFact(
                    **lineage,
                    kind="IP",
                    key=ip_address,
                    properties={"address": ip_address},
                ),
                GraphNodeFact(
                    **lineage,
                    kind="Service",
                    key=svc_key,
                    properties={
                        "service_key": svc_key,
                        "port": port,
                        "scheme": scheme,
                    },
                ),
                GraphNodeFact(
                    **lineage,
                    kind="Endpoint",
                    key=endpoint_key,
                    properties={
                        "service_method_normalized_path": endpoint_key,
                        "service_key": svc_key,
                        "method": method,
                        "normalized_path": normalized_path,
                        "status_code": _optional_int(row.get("status_code")),
                        "content_type": _optional_text(row.get("content_type")),
                        "url": _optional_text(row.get("url")),
                    },
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="Host",
                    src_key=hostname,
                    edge_kind="RESOLVES_TO",
                    dst_kind="IP",
                    dst_key=ip_address,
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="IP",
                    src_key=ip_address,
                    edge_kind="EXPOSES_SERVICE",
                    dst_kind="Service",
                    dst_key=svc_key,
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="Service",
                    src_key=svc_key,
                    edge_kind="HAS_ENDPOINT",
                    dst_kind="Endpoint",
                    dst_key=endpoint_key,
                ),
            ]
            for fact in candidates:
                if fact.identity_key not in seen:
                    seen.add(fact.identity_key)
                    facts.append(fact)

        if program_id is None or not facts:
            return None
        return GraphFactBatch(
            program_id=program_id,
            facts=facts,
            produced_by="httpx-observation-producer",
            parser_version=self._parser_version,
        )


def service_key(*, hostname: str, port: int, scheme: str) -> str:
    return f"{hostname.strip().lower()}:{int(port)}/{scheme.strip().lower()}"


def service_method_normalized_path_key(*, service_key: str, method: str, normalized_path: str) -> str:
    return f"{service_key}:{method.strip().upper()}:{normalized_path.strip()}"


def http_observations_dedupe_key(raw_artifact_id: UUID | str, parser_version: str) -> str:
    return f"http-observations:{raw_artifact_id}:{parser_version}"


def _required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    value = _optional_uuid(row.get(key))
    if value is None:
        raise ValueError(f"http observation row requires {key}")
    return value


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _required_text(row: Mapping[str, Any], key: str) -> str:
    text = _optional_text(row.get(key))
    if text is None:
        raise ValueError(f"http observation row requires non-empty {key}")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
```

- [ ] **Step 2: Run producer tests**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py -q
```

Expected: PASS for producer tests that do not require the enqueuer yet.

---

### Task 3: Repository Projection Event

**Files:**
- Modify: `src/api/infrastructure/repositories/adapters/http_observation.py`
- Test: `tests/infrastructure/test_http_observation_projection_event.py`

- [ ] **Step 1: Write failing repository event test**

Create `tests/infrastructure/test_http_observation_projection_event.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_http_observation_repository_enqueues_ready_projection_event() -> None:
    source = Path("src/api/infrastructure/repositories/adapters/http_observation.py").read_text(encoding="utf-8")

    assert "graph_projection_events" in source
    assert "http_observations_ready" in source
    assert "http-observations-ready:" in source
    assert "on_conflict_do_nothing" in source
    assert "raw_artifact_id is None" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_projection_event.py -q
```

Expected: FAIL because the repository does not insert projection events.

- [ ] **Step 3: Insert projection event in repository**

Modify `src/api/infrastructure/repositories/adapters/http_observation.py`:

```python
from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.adapters.orm import graph_projection_events
```

In `SQLAlchemyHTTPObservationRepository.create_with_headers`, after header rows are added and before `await self.session.flush()` returns, call:

```python
        await self._enqueue_graph_projection_event(created)
```

Add this private method to `SQLAlchemyHTTPObservationRepository`:

```python
    async def _enqueue_graph_projection_event(self, observation: HTTPObservationModel) -> None:
        if observation.raw_artifact_id is None:
            return
        if observation.run_id is None:
            return

        dedupe_key = f"http-observations-ready:{observation.raw_artifact_id}"
        statement = (
            insert(graph_projection_events)
            .values(
                program_id=observation.program_id,
                source_type="raw_artifact",
                source_id=observation.raw_artifact_id,
                event_type="http_observations_ready",
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
        await self.session.execute(statement)
```

- [ ] **Step 4: Run repository event test**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_projection_event.py -q
```

Expected: PASS.

---

### Task 4: HTTP Observation Enqueuer

**Files:**
- Modify: `services/graph-projector/graph_projector/producers/http_observations.py`
- Test: `tests/infrastructure/test_http_observation_graphfact_producer.py`

- [ ] **Step 1: Add failing enqueuer tests**

Append to `tests/infrastructure/test_http_observation_graphfact_producer.py`:

```python
class RecordingCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, query: str, parameters: dict[str, object] | None = None):
        self.calls.append((query, parameters or {}))

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows):
        self.cursor_obj = RecordingCursor(rows)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class RecordingStore:
    def __init__(self):
        self.calls = []

    def enqueue(self, batch, *, dedupe_key=None):
        self.calls.append((batch, dedupe_key))
        return uuid4()


def test_http_observation_enqueuer_claims_ready_events_and_enqueues_batch() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.http_observations import HttpObservationGraphFactEnqueuer

    event_id = uuid4()
    raw_artifact_id = uuid4()
    row = _observation_row(raw_artifact_id=raw_artifact_id)
    row["projection_event_id"] = event_id
    row["projection_event_attempts"] = 1
    connection = RecordingConnection([row])
    store = RecordingStore()

    result = HttpObservationGraphFactEnqueuer(connection=connection, store=store).enqueue_pending(limit=10)

    assert result.scanned == 1
    assert result.enqueued == 1
    assert result.skipped == 0
    claim_query = connection.cursor_obj.calls[0][0]
    assert "FROM graph_projection_events" in claim_query
    assert "http_observations_ready" in claim_query
    assert "JOIN http_observations" in claim_query
    assert "JOIN endpoints" in claim_query
    assert "JOIN services" in claim_query
    assert "JOIN ip_addresses" in claim_query
    assert "JOIN hosts" in claim_query
    assert store.calls[0][1] == f"http-observations:{raw_artifact_id}:http-observations.v1"
    assert any("SET status = 'processed'" in call[0] for call in connection.cursor_obj.calls)


def test_http_observation_enqueue_loop_stops_after_idle_threshold() -> None:
    import sys

    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.http_observations import (
        HttpObservationEnqueueLoopResult,
        HttpObservationEnqueueResult,
    )

    class SequenceEnqueuer:
        def __init__(self):
            self.results = [
                HttpObservationEnqueueResult(scanned=1, enqueued=1, skipped=0),
                HttpObservationEnqueueResult(scanned=0, enqueued=0, skipped=0),
                HttpObservationEnqueueResult(scanned=0, enqueued=0, skipped=0),
            ]
            self.calls = []

        def enqueue_pending(self, *, limit=100, program_id=None):
            self.calls.append((limit, program_id))
            return self.results.pop(0)

    slept: list[float] = []
    enqueuer = SequenceEnqueuer()

    result = HttpObservationEnqueueLoopResult.run(
        enqueuer,
        limit=25,
        program_id="00000000-0000-0000-0000-000000000001",
        idle_exit_after=2,
        poll_seconds=0.25,
        sleep=slept.append,
    )

    assert result.scanned == 1
    assert result.enqueued == 1
    assert result.empty == 2
    assert result.iterations == 3
    assert slept == [0.25]
    assert enqueuer.calls == [
        (25, "00000000-0000-0000-0000-000000000001"),
        (25, "00000000-0000-0000-0000-000000000001"),
        (25, "00000000-0000-0000-0000-000000000001"),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py -q
```

Expected: FAIL because `HttpObservationGraphFactEnqueuer` is not implemented.

- [ ] **Step 3: Implement enqueuer**

Add `HttpObservationGraphFactEnqueuer` to `services/graph-projector/graph_projector/producers/http_observations.py`:

```python
class HttpObservationGraphFactEnqueuer:
    def __init__(
        self,
        *,
        connection: HttpObservationConnection,
        store: GraphFactBatchStore,
        producer: HttpObservationGraphFactProducer | None = None,
        worker_id: str = "graph-projector-http-observation-enqueuer",
        lock_seconds: int = 300,
        max_attempts: int = 3,
    ) -> None:
        self._connection = connection
        self._store = store
        self._producer = producer or HttpObservationGraphFactProducer()
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts

    def enqueue_pending(self, *, limit: int = 100, program_id: UUID | str | None = None) -> HttpObservationEnqueueResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self._claim_rows(limit=limit, program_id=program_id)
        if not rows:
            return HttpObservationEnqueueResult()

        rows_by_event: dict[UUID, list[Mapping[str, Any]]] = {}
        attempts_by_event: dict[UUID, int] = {}
        raw_artifact_by_event: dict[UUID, UUID] = {}
        for row in rows:
            event_id = _required_uuid(row, "projection_event_id")
            rows_by_event.setdefault(event_id, []).append(row)
            attempts_by_event[event_id] = int(row.get("projection_event_attempts") or 1)
            raw_artifact_by_event[event_id] = _required_uuid(row, "raw_artifact_id")

        enqueued = 0
        skipped = 0
        for event_id, event_rows in rows_by_event.items():
            try:
                batch = self._producer.produce(event_rows)
                if batch is None:
                    skipped += 1
                    self._mark_projection_event_processed(event_id)
                    continue
                raw_artifact_id = raw_artifact_by_event[event_id]
                self._store.enqueue(
                    batch,
                    dedupe_key=http_observations_dedupe_key(raw_artifact_id, batch.parser_version),
                )
                self._mark_projection_event_processed(event_id)
                enqueued += 1
            except Exception as exc:
                self._mark_projection_event_failed(
                    event_id,
                    error=str(exc),
                    dead=attempts_by_event[event_id] >= self._max_attempts,
                )
                raise
        return HttpObservationEnqueueResult(scanned=len(rows_by_event), enqueued=enqueued, skipped=skipped)
```

Add `_claim_rows`, `_mark_projection_event_processed`, `_mark_projection_event_failed`, and `_optional_uuid_text` using the same structure as `RawArtifactGraphFactEnqueuer`, with this claim SQL:

```sql
WITH next_events AS (
    SELECT id
    FROM graph_projection_events
    WHERE source_type = 'raw_artifact'
      AND event_type = 'http_observations_ready'
      AND status IN ('pending', 'failed')
      AND available_at <= %(now)s
      AND attempts < %(max_attempts)s
      AND (locked_until IS NULL OR locked_until < %(now)s)
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
    ORDER BY available_at ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT %(limit)s
), locked_events AS (
    UPDATE graph_projection_events
    SET status = 'locked',
        locked_by = %(worker_id)s,
        locked_until = %(locked_until)s,
        attempts = attempts + 1,
        updated_at = %(now)s,
        last_error = NULL
    WHERE id IN (SELECT id FROM next_events)
    RETURNING id, source_id, attempts
)
SELECT
    locked_events.id AS projection_event_id,
    locked_events.attempts AS projection_event_attempts,
    ho.id AS observation_id,
    ho.program_id,
    ho.run_id,
    ho.raw_artifact_id,
    ho.source_tool,
    ho.method,
    ho.url,
    ho.status_code,
    ho.content_type,
    ho.observed_at,
    e.id AS endpoint_id,
    e.path,
    e.normalized_path,
    h.id AS host_id,
    h.host AS hostname,
    s.id AS service_id,
    s.scheme,
    s.port,
    ip.id AS ip_id,
    ip.address AS ip_address
FROM locked_events
JOIN http_observations ho ON ho.raw_artifact_id = locked_events.source_id
JOIN endpoints e ON e.id = ho.endpoint_id
JOIN hosts h ON h.id = e.host_id
JOIN services s ON s.id = ho.service_id
JOIN ip_addresses ip ON ip.id = s.ip_id
WHERE ho.run_id IS NOT NULL
  AND ho.raw_artifact_id IS NOT NULL
ORDER BY ho.observed_at ASC, ho.id ASC;
```

- [ ] **Step 4: Run producer/enqueuer tests**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py -q
```

Expected: PASS.

---

### Task 5: CLI, Settings, and Compose Service

**Files:**
- Modify: `services/graph-projector/graph_projector/settings.py`
- Modify: `services/graph-projector/graph_projector/__main__.py`
- Modify: `docker-compose.yml`
- Test: `tests/infrastructure/test_http_observation_graphfact_producer.py`

- [ ] **Step 1: Add failing CLI/compose contract test**

Append to `tests/infrastructure/test_http_observation_graphfact_producer.py`:

```python
def test_enqueue_http_observations_cli_and_compose_service_are_exposed() -> None:
    main_source = Path("services/graph-projector/graph_projector/__main__.py").read_text(encoding="utf-8")
    settings_source = Path("services/graph-projector/graph_projector/settings.py").read_text(encoding="utf-8")
    compose_source = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'subparsers.add_parser("enqueue-http-observations"' in main_source
    assert 'subparsers.add_parser("enqueue-http-observations-loop"' in main_source
    assert "HttpObservationEnqueueLoopResult" in main_source
    assert "HTTP_OBSERVATION_ENQUEUE_LIMIT" in settings_source
    assert "HTTP_OBSERVATION_ENQUEUE_POLL_SECONDS" in settings_source
    assert "graph-projector-http-observation-enqueuer" in compose_source
    assert 'command: ["enqueue-http-observations-loop"]' in compose_source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py::test_enqueue_http_observations_cli_and_compose_service_are_exposed -q
```

Expected: FAIL.

- [ ] **Step 3: Add settings**

Modify `GraphProjectorSettings` in `services/graph-projector/graph_projector/settings.py`:

```python
    http_observation_enqueue_limit: int = 100
    http_observation_enqueue_poll_seconds: float = 5.0
```

Add to `from_env`:

```python
            http_observation_enqueue_limit=_env_int("HTTP_OBSERVATION_ENQUEUE_LIMIT", default=100),
            http_observation_enqueue_poll_seconds=_env_float("HTTP_OBSERVATION_ENQUEUE_POLL_SECONDS", default=5.0),
```

- [ ] **Step 4: Add CLI commands**

Modify `services/graph-projector/graph_projector/__main__.py` imports:

```python
from .producers.http_observations import (
    HttpObservationEnqueueLoopResult,
    HttpObservationGraphFactEnqueuer,
    HttpObservationGraphFactProducer,
)
```

Add parsers:

```python
    enqueue_http_observations = subparsers.add_parser("enqueue-http-observations", help="Enqueue GraphFactBatch rows from canonical HTTP observations.")
    enqueue_http_observations.add_argument("--limit", type=int, default=None)
    enqueue_http_observations.add_argument("--program-id", default=None)
    enqueue_http_observations_loop = subparsers.add_parser("enqueue-http-observations-loop", help="Continuously enqueue GraphFactBatch rows from canonical HTTP observations.")
    enqueue_http_observations_loop.add_argument("--limit", type=int, default=None)
    enqueue_http_observations_loop.add_argument("--program-id", default=None)
    enqueue_http_observations_loop.add_argument("--max-iterations", type=int, default=None)
    enqueue_http_observations_loop.add_argument("--idle-exit-after", type=int, default=None)
    enqueue_http_observations_loop.add_argument("--poll-seconds", type=float, default=None)
```

Add command branches:

```python
    if args.command == "enqueue-http-observations":
        settings = GraphProjectorSettings.from_env()
        enqueuer = _build_http_observation_enqueuer(settings)
        limit = settings.http_observation_enqueue_limit if args.limit is None else args.limit
        result = enqueuer.enqueue_pending(limit=limit, program_id=args.program_id)
        print(
            "graph-projector enqueue-http-observations: "
            f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped}"
        )
        return 0

    if args.command == "enqueue-http-observations-loop":
        settings = GraphProjectorSettings.from_env()
        enqueuer = _build_http_observation_enqueuer(settings)
        limit = settings.http_observation_enqueue_limit if args.limit is None else args.limit
        poll_seconds = settings.http_observation_enqueue_poll_seconds if args.poll_seconds is None else args.poll_seconds
        result = HttpObservationEnqueueLoopResult.run(
            enqueuer,
            limit=limit,
            program_id=args.program_id,
            max_iterations=args.max_iterations,
            idle_exit_after=args.idle_exit_after,
            poll_seconds=poll_seconds,
        )
        print(
            "graph-projector enqueue-http-observations-loop: "
            f"scanned={result.scanned} enqueued={result.enqueued} skipped={result.skipped} "
            f"empty={result.empty} iterations={result.iterations}"
        )
        return 0
```

Add builder:

```python
def _build_http_observation_enqueuer(settings: GraphProjectorSettings) -> HttpObservationGraphFactEnqueuer:
    connection = connect_postgres(settings.postgres_dsn)
    store = GraphFactBatchStore(connection)
    producer = HttpObservationGraphFactProducer()
    return HttpObservationGraphFactEnqueuer(
        connection=connection,
        store=store,
        producer=producer,
        worker_id=settings.worker_id,
        lock_seconds=settings.batch_lock_seconds,
        max_attempts=settings.batch_max_attempts,
    )
```

- [ ] **Step 5: Add compose service**

Add to `docker-compose.yml` under graph services:

```yaml
  graph-projector-http-observation-enqueuer:
    build:
      context: ./services/graph-projector
      dockerfile: Dockerfile
    container_name: bb-graph-projector-http-observation-enqueuer
    profiles:
      - graph
    env_file:
      - .env
    environment:
      PYTHONPATH: /app
      POSTGRES_HOST: ${POSTGRES_HOST:-postgres}
      POSTGRES_PORT: ${POSTGRES_PORT:-5432}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      HTTP_OBSERVATION_ENQUEUE_LIMIT: ${HTTP_OBSERVATION_ENQUEUE_LIMIT:-100}
      HTTP_OBSERVATION_ENQUEUE_POLL_SECONDS: ${HTTP_OBSERVATION_ENQUEUE_POLL_SECONDS:-5}
    command: ["enqueue-http-observations-loop"]
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
```

- [ ] **Step 6: Run CLI/compose test**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py::test_enqueue_http_observations_cli_and_compose_service_are_exposed -q
```

Expected: PASS.

---

### Task 6: Integration Coverage

**Files:**
- Create: `tests/integration/test_http_observation_projection_events.py`
- Test: integration Postgres stack

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_http_observation_projection_events.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.integration


def test_http_observation_ready_event_can_be_inserted_and_claimed(integration_sync_engine) -> None:
    program_id = uuid4()
    raw_artifact_id = uuid4()

    with integration_sync_engine.begin() as connection:
        connection.execute(text("INSERT INTO programs (id, name) VALUES (:id, :name)"), {"id": program_id, "name": "e2e-test"})
        connection.execute(
            text(
                """
                INSERT INTO graph_projection_events (
                    program_id, source_type, source_id, event_type, dedupe_key
                ) VALUES (
                    :program_id, 'raw_artifact', :source_id, 'http_observations_ready', :dedupe_key
                )
                ON CONFLICT (dedupe_key) DO NOTHING
                """
            ),
            {
                "program_id": program_id,
                "source_id": raw_artifact_id,
                "dedupe_key": f"http-observations-ready:{raw_artifact_id}",
            },
        )

    with integration_sync_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT source_type, event_type, status
                FROM graph_projection_events
                WHERE dedupe_key = :dedupe_key
                """
            ),
            {"dedupe_key": f"http-observations-ready:{raw_artifact_id}"},
        ).mappings().one()

    assert row["source_type"] == "raw_artifact"
    assert row["event_type"] == "http_observations_ready"
    assert row["status"] == "pending"
```

- [ ] **Step 2: Run integration test**

Run with the isolated stack running:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest tests/integration/test_http_observation_projection_events.py -q
```

Expected: PASS after migrations are already valid.

---

### Task 7: E2E Harness and Graph Test

**Files:**
- Modify: `pytest.ini`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_httpx_to_neo4j_graph.py`

- [ ] **Step 1: Register e2e marker**

Modify `pytest.ini`:

```ini
markers =
    integration: tests requiring isolated dockerized external services
    e2e: tests requiring isolated Postgres and Neo4j services
```

- [ ] **Step 2: Create e2e fixtures**

Create `tests/e2e/conftest.py`:

```python
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env.integration"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: tests requiring isolated Postgres and Neo4j services")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_E2E_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_E2E_TESTS=1 to run e2e tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@pytest.fixture(scope="session")
def e2e_postgres_url() -> str:
    _load_env()
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "55432")
    database = os.getenv("POSTGRES_DB", "bugbounty_integration_test")
    user = os.getenv("POSTGRES_USER", "bugbounty_integration_test")
    password = os.getenv("POSTGRES_PASSWORD", "bugbounty_integration_test")
    joined = " ".join([host, port, database, user]).lower()
    if port in {"5432", "6432"} and host in {"localhost", "127.0.0.1", "postgres"}:
        raise RuntimeError(f"Refusing to run e2e tests against default Postgres port: {host}:{port}")
    if "test" not in joined and "integration" not in joined:
        raise RuntimeError(f"Refusing to run e2e tests against non-test database settings: {joined}")
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{quote_plus(database)}"
    )


@pytest.fixture(scope="session")
def e2e_postgres_engine(e2e_postgres_url: str):
    url = e2e_postgres_url.replace("postgresql+psycopg2://", "postgresql://")
    os.environ["DATABASE_URL"] = url
    config = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(e2e_postgres_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def e2e_neo4j_driver():
    _load_env()
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", f"bolt://localhost:{os.getenv('NEO4J_BOLT_PORT', '57687')}")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "bugbounty-integration-test")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=os.getenv("NEO4J_DATABASE", "neo4j")) as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
        yield driver
    finally:
        driver.close()
```

- [ ] **Step 3: Write e2e graph test**

Create `tests/e2e/test_httpx_to_neo4j_graph.py`:

```python
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
    from graph_projector.batch_store import GraphFactBatchStore
    from graph_projector.producers.http_observations import HttpObservationGraphFactEnqueuer
    from graph_projector.writer import GraphFactWriter, GraphOntologyRegistry
    from graph_projector.ontology import default_graph_ontology

    return (
        GraphFactBatchApplicator,
        GraphFactBatchStore,
        HttpObservationGraphFactEnqueuer,
        GraphFactWriter,
        GraphOntologyRegistry,
        default_graph_ontology,
    )


def test_fake_httpx_canonical_observation_projects_endpoint_graph(e2e_postgres_engine, e2e_neo4j_driver) -> None:
    (
        GraphFactBatchApplicator,
        GraphFactBatchStore,
        HttpObservationGraphFactEnqueuer,
        GraphFactWriter,
        GraphOntologyRegistry,
        default_graph_ontology,
    ) = _graph_symbols()

    program_id = uuid4()
    raw_artifact_id = uuid4()
    run_id = uuid4()
    job_id = uuid4()
    host_id = uuid4()
    ip_id = uuid4()
    service_id = uuid4()
    endpoint_id = uuid4()
    observation_id = uuid4()

    with e2e_postgres_engine.begin() as connection:
        connection.execute(text("INSERT INTO programs (id, name) VALUES (:id, :name)"), {"id": program_id, "name": "e2e-httpx-graph"})
        connection.execute(text("INSERT INTO jobs (id, program_id, node_id, event_name, status) VALUES (:id, :program_id, 'httpx', 'httpx_scan_requested', 'completed')"), {"id": job_id, "program_id": program_id})
        connection.execute(text("INSERT INTO runs (id, job_id, program_id, node_id, event_name, status) VALUES (:id, :job_id, :program_id, 'httpx', 'httpx_scan_requested', 'completed')"), {"id": run_id, "job_id": job_id, "program_id": program_id})
        connection.execute(text("INSERT INTO raw_artifacts (id, program_id, job_id, run_id, node_id, event_name, artifact_type, storage_uri, sha256, size_bytes, artifact_metadata) VALUES (:id, :program_id, :job_id, :run_id, 'httpx', 'httpx.completed', 'raw_tool_output', 'raw://httpx.ndjson', :sha256, 123, '{}')"), {"id": raw_artifact_id, "program_id": program_id, "job_id": job_id, "run_id": run_id, "sha256": "a" * 64})
        connection.execute(text("INSERT INTO hosts (id, program_id, host, in_scope, cname) VALUES (:id, :program_id, 'api.example.com', true, '[]')"), {"id": host_id, "program_id": program_id})
        connection.execute(text("INSERT INTO ip_addresses (id, program_id, address, in_scope) VALUES (:id, :program_id, '203.0.113.10', true)"), {"id": ip_id, "program_id": program_id})
        connection.execute(text("INSERT INTO host_ips (host_id, ip_id, source) VALUES (:host_id, :ip_id, 'httpx')"), {"host_id": host_id, "ip_id": ip_id})
        connection.execute(text("INSERT INTO services (id, ip_id, scheme, port, technologies, websocket) VALUES (:id, :ip_id, 'https', 443, '{}', false)"), {"id": service_id, "ip_id": ip_id})
        connection.execute(text("INSERT INTO endpoints (id, host_id, service_id, path, normalized_path, methods, status_code) VALUES (:id, :host_id, :service_id, '/v1/users/123', '/v1/users/{id}', ARRAY['GET'], 200)"), {"id": endpoint_id, "host_id": host_id, "service_id": service_id})
        connection.execute(text("INSERT INTO http_observations (id, program_id, endpoint_id, service_id, job_id, run_id, raw_artifact_id, method, url, status_code, content_type, source_tool, metadata) VALUES (:id, :program_id, :endpoint_id, :service_id, :job_id, :run_id, :raw_artifact_id, 'GET', 'https://api.example.com/v1/users/123', 200, 'application/json', 'httpx', '{}')"), {"id": observation_id, "program_id": program_id, "endpoint_id": endpoint_id, "service_id": service_id, "job_id": job_id, "run_id": run_id, "raw_artifact_id": raw_artifact_id})
        connection.execute(text("INSERT INTO graph_projection_events (program_id, source_type, source_id, event_type, dedupe_key) VALUES (:program_id, 'raw_artifact', :source_id, 'http_observations_ready', :dedupe_key) ON CONFLICT (dedupe_key) DO NOTHING"), {"program_id": program_id, "source_id": raw_artifact_id, "dedupe_key": f"http-observations-ready:{raw_artifact_id}"})

    raw_connection = e2e_postgres_engine.raw_connection()
    try:
        store = GraphFactBatchStore(raw_connection)
        result = HttpObservationGraphFactEnqueuer(connection=raw_connection, store=store).enqueue_pending(limit=10, program_id=program_id)
        assert result.enqueued == 1
    finally:
        raw_connection.close()

    raw_connection = e2e_postgres_engine.raw_connection()
    try:
        applicator = GraphFactBatchApplicator(
            store=GraphFactBatchStore(raw_connection),
            neo4j_driver=e2e_neo4j_driver,
            writer=GraphFactWriter(GraphOntologyRegistry(default_graph_ontology())),
            neo4j_database="neo4j",
            worker_id="e2e",
            lock_seconds=300,
            max_attempts=3,
        )
        assert applicator.apply_one().status == "applied"
        assert applicator.apply_one().status == "empty"
    finally:
        raw_connection.close()

    with e2e_neo4j_driver.session(database="neo4j") as session:
        counts = session.run(
            """
            MATCH (h:Host {hostname: 'api.example.com'})-[:RESOLVES_TO]->(ip:IP {address: '203.0.113.10'})
            MATCH (ip)-[:EXPOSES_SERVICE]->(s:Service {service_key: 'api.example.com:443/https'})
            MATCH (s)-[:HAS_ENDPOINT]->(e:Endpoint {service_method_normalized_path: 'api.example.com:443/https:GET:/v1/users/{id}'})
            RETURN count(DISTINCT h) AS hosts,
                   count(DISTINCT ip) AS ips,
                   count(DISTINCT s) AS services,
                   count(DISTINCT e) AS endpoints
            """
        ).mappings().one()

    assert counts["hosts"] == 1
    assert counts["ips"] == 1
    assert counts["services"] == 1
    assert counts["endpoints"] == 1
```

- [ ] **Step 4: Run e2e test**

Run with the isolated stack running:

```bash
RUN_E2E_TESTS=1 python -m pytest tests/e2e/test_httpx_to_neo4j_graph.py -q
```

Expected: PASS.

---

### Task 8: Documentation and Full Verification

**Files:**
- Modify: `docs/testing/integration-tests.md`
- Verify: targeted and full test suites

- [ ] **Step 1: Document e2e workflow**

Append to `docs/testing/integration-tests.md`:

```markdown
## E2E Graph Tests

Graph e2e tests are skipped unless `RUN_E2E_TESTS=1` is set. They use the same
isolated Docker stack as integration tests and verify the complete projection
path from canonical HTTP observations to Neo4j graph relationships.

Start the isolated stack:

```bash
docker compose -f docker-compose.integration.yml --env-file .env.integration up -d postgres-integration neo4j-integration
```

Run graph e2e tests:

```bash
RUN_E2E_TESTS=1 python -m pytest -q -m e2e
```

Windows PowerShell:

```powershell
$env:RUN_E2E_TESTS="1"; python -m pytest -q -m e2e
```

These tests use deterministic test data and must not invoke real scanner
binaries.
```

- [ ] **Step 2: Run targeted unit tests**

Run:

```bash
python -m pytest tests/infrastructure/test_http_observation_graphfact_producer.py tests/infrastructure/test_http_observation_projection_event.py tests/infrastructure/test_graph_projection_events.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full unit suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS with existing skipped tests unchanged.

- [ ] **Step 4: Run integration tests**

Run:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -q -m integration
```

Expected: PASS.

- [ ] **Step 5: Run e2e graph tests**

Run:

```bash
RUN_E2E_TESTS=1 python -m pytest -q -m e2e
```

Expected: PASS.

- [ ] **Step 6: Commit implementation**

Run:

```bash
git add services/graph-projector/graph_projector/producers/http_observations.py services/graph-projector/graph_projector/__main__.py services/graph-projector/graph_projector/settings.py src/api/infrastructure/repositories/adapters/http_observation.py tests/infrastructure/test_http_observation_graphfact_producer.py tests/infrastructure/test_http_observation_projection_event.py tests/infrastructure/test_graph_projection_events.py docker-compose.yml pytest.ini tests/e2e/conftest.py tests/e2e/test_httpx_to_neo4j_graph.py docs/testing/integration-tests.md
git commit -m "feat: project http observations to graph facts"
```

---

## Self-Review

Spec coverage:

- Production `HttpObservationGraphFactProducer`: covered by Tasks 1 and 2.
- Durable post-canonical projection event: covered by Task 3.
- Enqueuer and loop command: covered by Tasks 4 and 5.
- No real scanner e2e path: covered by Task 7 through direct deterministic canonical data. A later refinement can replace direct inserts with a fake `ScanNode` runner once the first graph e2e is stable.
- Neo4j assertions for `Host`, `IP`, `Service`, `Endpoint`, `RESOLVES_TO`, `EXPOSES_SERVICE`, and `HAS_ENDPOINT`: covered by Task 7.
- Verification commands: covered by Task 8.

Type consistency:

- The producer uses existing `GraphNodeFact`, `GraphEdgeFact`, `GraphFactBatch`, and `GraphFactBatchStore`.
- The enqueuer follows the existing raw artifact enqueuer shape.
- The projection event reuses existing `graph_projection_events` columns and does not require an Alembic schema migration.

Risk notes:

- Task 7 starts with deterministic canonical inserts instead of a full `ScanNode` fake runner. This gives a stable Postgres-to-Neo4j e2e first. After this passes, add a second e2e that routes fake `httpx` JSONL through `ScanNode`, `HTTPXProcessEventParser`, `HTTPXBatchProcessor`, and `HTTPXResultIngestor`.
- The repository event insert is PostgreSQL-specific because it uses `on_conflict_do_nothing`. Existing production projection queues already target PostgreSQL, so this matches current infrastructure.
