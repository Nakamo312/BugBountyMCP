from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from .contracts import GraphFactBatch
from .row_codec import adapt_json_parameters_for_cursor, cursor_for


_BATCH_EXCLUDE = {
    "facts": {"__all__": {"identity_key"}},
}


_GRAPH_FACT_BATCH_INSERT_RESET = """
INSERT INTO graph_fact_batches (
    id,
    program_id,
    produced_by,
    parser_version,
    dedupe_key,
    facts_json,
    fact_count
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(produced_by)s,
    %(parser_version)s,
    %(dedupe_key)s,
    %(facts_json)s,
    %(fact_count)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET program_id = EXCLUDED.program_id,
    produced_by = EXCLUDED.produced_by,
    parser_version = EXCLUDED.parser_version,
    facts_json = EXCLUDED.facts_json,
    fact_count = EXCLUDED.fact_count,
    status = 'pending',
    attempts = 0,
    applied_at = NULL,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL,
    available_at = now(),
    updated_at = now()
RETURNING id;
""".strip()

_GRAPH_FACT_BATCH_INSERT_KEEP_EXISTING = """
INSERT INTO graph_fact_batches (
    id,
    program_id,
    produced_by,
    parser_version,
    dedupe_key,
    facts_json,
    fact_count
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(produced_by)s,
    %(parser_version)s,
    %(dedupe_key)s,
    %(facts_json)s,
    %(fact_count)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET updated_at = graph_fact_batches.updated_at
RETURNING id;
""".strip()


class Cursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchone(self) -> dict[str, Any] | None: ...


class Connection(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> object: ...
    def rollback(self) -> object: ...


@dataclass(frozen=True)
class ClaimedGraphFactBatch:
    batch_id: UUID
    batch: GraphFactBatch
    attempts: int


def serialize_graph_fact_batch(batch: GraphFactBatch) -> dict[str, object]:
    """Return database-ready values for a durable GraphFactBatch row."""

    facts_json = batch.model_dump(mode="json", exclude=_BATCH_EXCLUDE)
    return {
        "program_id": str(batch.program_id),
        "produced_by": batch.produced_by,
        "parser_version": batch.parser_version,
        "facts_json": facts_json,
        "fact_count": len(batch.facts),
    }


def deserialize_graph_fact_batch(payload: dict[str, Any]) -> GraphFactBatch:
    """Rehydrate a GraphFactBatch from the JSON payload stored in PostgreSQL."""

    return GraphFactBatch.model_validate(payload)


class GraphFactBatchStore:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def enqueue(self, batch: GraphFactBatch, *, dedupe_key: str | None = None, reset_existing: bool = False) -> UUID:
        values = serialize_graph_fact_batch(batch)
        values["id"] = str(uuid4())
        values["dedupe_key"] = _dedupe_key(dedupe_key)
        row = self._fetchone(
            _graph_fact_batch_insert_statement(reset_existing=reset_existing),
            values,
        )
        if row is None:
            self._connection.rollback()
            raise RuntimeError("graph_fact_batches insert did not return an id")
        self._connection.commit()
        return UUID(str(row["id"]))

    def claim_next(self, *, worker_id: str, lock_seconds: int, max_attempts: int) -> ClaimedGraphFactBatch | None:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=lock_seconds)
        row = self._fetchone(
            """
WITH next_batch AS (
    SELECT id
    FROM graph_fact_batches
    WHERE status IN ('pending', 'failed')
      AND available_at <= %(now)s
      AND attempts < %(max_attempts)s
      AND (locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY available_at ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE graph_fact_batches
SET status = 'locked',
    locked_by = %(worker_id)s,
    locked_until = %(locked_until)s,
    attempts = attempts + 1,
    updated_at = %(now)s,
    last_error = NULL
WHERE id = (SELECT id FROM next_batch)
RETURNING id, facts_json, attempts;
""".strip(),
            {
                "worker_id": worker_id,
                "now": now,
                "locked_until": locked_until,
                "max_attempts": max_attempts,
            },
        )
        if row is None:
            self._connection.commit()
            return None
        self._connection.commit()
        return ClaimedGraphFactBatch(
            batch_id=row["id"],
            batch=deserialize_graph_fact_batch(row["facts_json"]),
            attempts=int(row["attempts"]),
        )

    def mark_applied(self, batch_id: UUID, *, worker_id: str) -> None:
        now = datetime.now(UTC)
        self._execute(
            """
UPDATE graph_fact_batches
SET status = 'applied',
    applied_at = %(now)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = %(batch_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip(),
            {"batch_id": batch_id, "now": now, "worker_id": worker_id},
        )
        self._connection.commit()

    def mark_failed(self, batch_id: UUID, *, error: str, dead: bool, worker_id: str) -> None:
        now = datetime.now(UTC)
        status = "dead" if dead else "failed"
        self._execute(
            """
UPDATE graph_fact_batches
SET status = %(status)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %(error)s
WHERE id = %(batch_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip(),
            {"batch_id": batch_id, "status": status, "now": now, "error": error[:4000], "worker_id": worker_id},
        )
        self._connection.commit()

    def _execute(self, query: str, parameters: dict[str, object]) -> None:
        cursor = self._cursor()
        try:
            cursor.execute(query, parameters)
        except Exception:
            self._connection.rollback()
            raise

    def _fetchone(self, query: str, parameters: dict[str, object]) -> dict[str, Any] | None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
            return cursor.fetchone()
        except Exception:
            self._connection.rollback()
            raise

    def _cursor(self) -> Cursor:
        return cursor_for(self._connection)


def connect_postgres(dsn: str) -> Connection:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on service image
        raise RuntimeError(
            "PostgreSQL projection is enabled but the graph-projector service is missing psycopg2-binary."
        ) from exc

    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def _graph_fact_batch_insert_statement(*, reset_existing: bool) -> str:
    return _GRAPH_FACT_BATCH_INSERT_RESET if reset_existing else _GRAPH_FACT_BATCH_INSERT_KEEP_EXISTING


def _dedupe_key(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("dedupe_key must not be empty")
    return stripped


_GRAPH_FACT_BATCH_JSON_KEYS = frozenset({"facts_json"})


def _adapt_json_parameters_for_cursor(cursor: Cursor, parameters: dict[str, object]) -> dict[str, object]:
    return adapt_json_parameters_for_cursor(cursor, parameters, json_keys=_GRAPH_FACT_BATCH_JSON_KEYS)
