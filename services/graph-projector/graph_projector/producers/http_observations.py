from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
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

        scanned = 0
        enqueued = 0
        skipped = 0
        empty = 0
        iterations = 0
        consecutive_empty = 0

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

        return HttpObservationEnqueueLoopResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped=skipped,
            empty=empty,
            iterations=iterations,
        )


class HttpObservationGraphFactProducer:
    def __init__(self, *, parser_version: str = "http-observations.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        facts = []
        seen_fact_keys: set[tuple[str, UUID, UUID]] = set()
        batch_program_id: UUID | None = None

        for row in rows:
            source_tool = _optional_text(row.get("source_tool"))
            if source_tool is None or source_tool.lower() != "httpx":
                continue

            run_id = _optional_uuid(row.get("run_id"))
            raw_artifact_id = _optional_uuid(row.get("raw_artifact_id"))
            if run_id is None or raw_artifact_id is None:
                continue

            program_id = _required_uuid(row, "program_id")
            if batch_program_id is None:
                batch_program_id = program_id
            elif batch_program_id != program_id:
                raise ValueError("http observation batch cannot mix program_id values")

            hostname = _canonical_hostname(_required_text(row, "hostname"))
            canonical_ip_address = _canonical_ip_address(_required_text(row, "ip_address"))
            scheme = _required_text(row, "scheme").lower()
            port = _required_int(row, "port")
            method = _required_text(row, "method").upper()
            normalized_path = _required_text(row, "normalized_path")
            svc_key = service_key(hostname=hostname, port=port, scheme=scheme)
            endpoint_key = service_method_normalized_path_key(
                service_key=svc_key,
                method=method,
                normalized_path=normalized_path,
            )
            lineage = {
                "program_id": program_id,
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
                    key=canonical_ip_address,
                    properties={"address": canonical_ip_address},
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
                    dst_key=canonical_ip_address,
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="IP",
                    src_key=canonical_ip_address,
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
                dedupe_key = (fact.identity_key, fact.source_artifact_id, fact.tool_run_id)
                if dedupe_key in seen_fact_keys:
                    continue
                seen_fact_keys.add(dedupe_key)
                facts.append(fact)

        if batch_program_id is None or not facts:
            return None
        return GraphFactBatch(
            program_id=batch_program_id,
            facts=facts,
            produced_by="httpx-observation-producer",
            parser_version=self._parser_version,
        )


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
        grouped_rows: "OrderedDict[UUID, list[Mapping[str, Any]]]" = OrderedDict()
        for row in rows:
            event_id = _required_uuid(row, "projection_event_id")
            grouped_rows.setdefault(event_id, []).append(row)

        enqueued = 0
        skipped = 0
        for event_id, event_rows in grouped_rows.items():
            try:
                batch = self._producer.produce(event_rows)
                if batch is None:
                    skipped += 1
                    self._mark_projection_event_processed(event_id)
                    continue

                raw_artifact_id = _first_required_raw_artifact_id(event_rows)
                self._store.enqueue(
                    batch,
                    dedupe_key=http_observations_dedupe_key(raw_artifact_id, batch.parser_version),
                )
                self._mark_projection_event_processed(event_id)
                enqueued += 1
            except Exception as exc:
                attempts = int(event_rows[0].get("projection_event_attempts") or 1)
                self._mark_projection_event_failed(
                    event_id,
                    error=str(exc),
                    dead=attempts >= self._max_attempts,
                )
                raise

        return HttpObservationEnqueueResult(scanned=len(grouped_rows), enqueued=enqueued, skipped=skipped)

    def _claim_rows(self, *, limit: int, program_id: UUID | str | None) -> list[Mapping[str, Any]]:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=self._lock_seconds)
        query = """
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
    RETURNING id, program_id, source_id, attempts
)
SELECT
    locked_events.id AS projection_event_id,
    locked_events.attempts AS projection_event_attempts,
    locked_events.source_id AS event_raw_artifact_id,
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
LEFT JOIN http_observations ho
    ON ho.raw_artifact_id = locked_events.source_id
   AND ho.run_id IS NOT NULL
   AND ho.raw_artifact_id IS NOT NULL
   AND ho.source_tool = 'httpx'
LEFT JOIN endpoints e ON e.id = ho.endpoint_id
LEFT JOIN hosts h ON h.id = e.host_id
LEFT JOIN services s ON s.id = ho.service_id
LEFT JOIN ip_addresses ip ON ip.id = s.ip_id
LEFT JOIN host_ips hi ON hi.host_id = h.id AND hi.ip_id = ip.id
ORDER BY locked_events.id ASC, ho.observed_at ASC, ho.id ASC;
""".strip()
        cursor = self._connection.cursor()
        cursor.execute(
            query,
            {
                "limit": limit,
                "program_id": _optional_uuid_text(program_id),
                "now": now,
                "locked_until": locked_until,
                "worker_id": self._worker_id,
                "max_attempts": self._max_attempts,
            },
        )
        rows = list(cursor.fetchall())
        if hasattr(self._connection, "commit"):
            self._connection.commit()
        return rows

    def _mark_projection_event_processed(self, event_id: UUID) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            """
UPDATE graph_projection_events
SET status = 'processed',
    processed_at = %(now)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip(),
            {"event_id": event_id, "now": now, "worker_id": self._worker_id},
        )
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def _mark_projection_event_failed(self, event_id: UUID, *, error: str, dead: bool) -> None:
        now = datetime.now(UTC)
        cursor = self._connection.cursor()
        cursor.execute(
            """
UPDATE graph_projection_events
SET status = %(status)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %(error)s
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip(),
            {
                "event_id": event_id,
                "status": "dead" if dead else "failed",
                "now": now,
                "error": error[:4000],
                "worker_id": self._worker_id,
            },
        )
        if hasattr(self._connection, "commit"):
            self._connection.commit()


def service_key(*, hostname: str, port: int, scheme: str) -> str:
    return f"{_canonical_hostname(hostname)}:{int(port)}/{scheme.strip().lower()}"


def service_method_normalized_path_key(*, service_key: str, method: str, normalized_path: str) -> str:
    return f"{service_key.strip()}:{method.strip().upper()}:{normalized_path.strip()}"


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


def _optional_uuid_text(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(_optional_uuid(value))


def _first_required_raw_artifact_id(rows: list[Mapping[str, Any]]) -> UUID:
    for row in rows:
        value = _optional_uuid(row.get("raw_artifact_id"))
        if value is not None:
            return value
    raise ValueError("http observation batch requires raw_artifact_id")


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


def _canonical_hostname(value: str) -> str:
    hostname = value.strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("http observation row requires non-empty hostname")
    return hostname


def _canonical_ip_address(value: str) -> str:
    text = value.strip()
    try:
        return str(ip_address(text))
    except ValueError:
        return text


def _required_int(row: Mapping[str, Any], key: str) -> int:
    if row.get(key) is None:
        raise ValueError(f"http observation row requires {key}")
    return int(row[key])


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
