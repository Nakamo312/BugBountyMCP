from __future__ import annotations

from time import sleep as default_sleep
from typing import Any, Callable, Mapping
from uuid import UUID

from .row_codec import cursor_for, optional_uuid_text as _optional_uuid_text
from .surface_component_analysis_event_models import (
    ClaimedSurfaceComponentAnalysisEvent,
    SurfaceAnalysisEventConnection,
    SurfaceAnalysisEventCursor,
    SurfaceComponentAnalysisEvent,
    SurfaceComponentAnalysisEventLoopResult,
    SurfaceComponentAnalysisEventProcessResult,
)
from .surface_component_analysis_event_statements import (
    SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING_SQL,
    SEARCH_PROJECTION_EVENT_INSERT_RESET_SQL,
    SURFACE_ANALYSIS_EVENT_CLAIM_NEXT_SQL,
    SURFACE_ANALYSIS_EVENT_INSERT_KEEP_EXISTING_SQL,
    SURFACE_ANALYSIS_EVENT_INSERT_RESET_SQL,
    SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL,
    SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL,
    SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_DELTA_SQL,
    SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_SNAPSHOT_SQL,
    SURFACE_COMPONENT_ANALYSIS_EVENT_TYPE,
    SURFACE_COMPONENT_ANALYSIS_VERSION,
    adapt_surface_analysis_event_json_parameters,
    claimed_surface_analysis_event_from_row,
    claim_next_surface_analysis_event_values,
    mark_failed_surface_analysis_event_values,
    mark_processed_surface_analysis_event_values,
    previous_snapshot_values,
    search_projection_event_insert_statement as _search_projection_event_insert_statement,
    search_projection_event_insert_values,
    surface_analysis_event_insert_statement as _surface_analysis_event_insert_statement,
    surface_analysis_event_insert_values,
)
from .surface_component_materialization import SurfaceComponentAnalysisStore, SurfaceComponentMaterializationResult
from .surface_component_report import SurfaceComponentReportReader


class SurfaceComponentAnalysisEventStore:
    """Durable queue for Surface Component analysis materialization.

    The queue is intentionally separate from graph_projection_events. Graph
    projection events move canonical state into Neo4j. These rows start after
    the Surface Map graph has been applied and request a downstream GDS report
    to be materialized back into PostgreSQL.
    """

    def __init__(self, connection: SurfaceAnalysisEventConnection) -> None:
        self._connection = connection

    def enqueue_surface_map_projected(
        self,
        *,
        program_id: UUID | str,
        snapshot_id: UUID | str,
        previous_snapshot_id: UUID | str | None = None,
        event_type: str = SURFACE_COMPONENT_ANALYSIS_EVENT_TYPE,
        analysis_version: str = SURFACE_COMPONENT_ANALYSIS_VERSION,
        settings_json: Mapping[str, Any] | None = None,
        reset_existing: bool = False,
    ) -> UUID:
        if not str(event_type).strip():
            raise ValueError("event_type must not be empty")
        if not str(analysis_version).strip():
            raise ValueError("analysis_version must not be empty")
        resolved_previous = _optional_uuid_text(previous_snapshot_id) or self._previous_snapshot_id(
            program_id=program_id,
            snapshot_id=snapshot_id,
        )
        row = self._fetchone(
            _surface_analysis_event_insert_statement(reset_existing=reset_existing),
            surface_analysis_event_insert_values(
                program_id=program_id,
                snapshot_id=snapshot_id,
                previous_snapshot_id=resolved_previous,
                event_type=event_type,
                analysis_version=analysis_version,
                settings_json=settings_json,
                dedupe_key=_dedupe_key(
                    program_id=program_id,
                    snapshot_id=snapshot_id,
                    event_type=event_type,
                    analysis_version=analysis_version,
                ),
            ),
        )
        if row is None:
            self._connection.rollback()
            raise RuntimeError("surface_component_analysis_events insert did not return an id")
        self._connection.commit()
        return UUID(str(row["id"]))

    def claim_next(
        self,
        *,
        worker_id: str,
        lock_seconds: int,
        max_attempts: int,
        program_id: UUID | str | None = None,
    ) -> ClaimedSurfaceComponentAnalysisEvent | None:
        row = self._fetchone(
            SURFACE_ANALYSIS_EVENT_CLAIM_NEXT_SQL,
            claim_next_surface_analysis_event_values(
                worker_id=worker_id,
                lock_seconds=lock_seconds,
                max_attempts=max_attempts,
                program_id=program_id,
            ),
        )
        if row is None:
            self._connection.commit()
            return None
        self._connection.commit()
        return claimed_surface_analysis_event_from_row(row)

    def mark_processed(
        self,
        event_id: UUID,
        *,
        materialization: SurfaceComponentMaterializationResult,
        worker_id: str,
    ) -> None:
        self._execute(
            SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL,
            mark_processed_surface_analysis_event_values(
                event_id=event_id,
                materialization=materialization,
                worker_id=worker_id,
            ),
        )
        self._connection.commit()

    def mark_failed(self, event_id: UUID, *, error: str, dead: bool, worker_id: str) -> None:
        self._execute(
            SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL,
            mark_failed_surface_analysis_event_values(event_id=event_id, error=error, dead=dead, worker_id=worker_id),
        )
        self._connection.commit()

    def _previous_snapshot_id(self, *, program_id: UUID | str, snapshot_id: UUID | str) -> str | None:
        parameters = previous_snapshot_values(program_id=program_id, snapshot_id=snapshot_id)
        row = self._fetchone(SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_DELTA_SQL, parameters)
        if row and row.get("from_snapshot_id") is not None:
            return str(row["from_snapshot_id"])
        row = self._fetchone(SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_SNAPSHOT_SQL, parameters)
        if row and row.get("id") is not None:
            return str(row["id"])
        return None

    def _execute(self, query: str, parameters: dict[str, object]) -> None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
        except Exception:
            self._connection.rollback()
            raise

    def _fetchone(self, query: str, parameters: dict[str, object]) -> Mapping[str, Any] | None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
            return cursor.fetchone()
        except Exception:
            self._connection.rollback()
            raise

    def _cursor(self) -> SurfaceAnalysisEventCursor:
        return cursor_for(self._connection)


class SearchProjectionEventPublisher:
    """Write downstream OpenSearch projection events without importing search-indexer."""

    def __init__(self, connection: SurfaceAnalysisEventConnection) -> None:
        self._connection = connection

    def enqueue_surface_component_outputs(
        self,
        *,
        program_id: UUID | str,
        analysis_run_id: UUID | str,
        snapshot_id: UUID | str,
        reset_existing: bool = False,
    ) -> tuple[UUID, UUID]:
        component_event_id = self.enqueue(
            program_id=program_id,
            target="surface-components",
            source_type="surface_component_analysis_run",
            source_id=analysis_run_id,
            filters_json={"analysis_run_id": str(analysis_run_id)},
            reset_existing=reset_existing,
        )
        delta_event_id = self.enqueue(
            program_id=program_id,
            target="surface-deltas",
            source_type="surface_snapshot",
            source_id=snapshot_id,
            filters_json={"snapshot_id": str(snapshot_id)},
            reset_existing=reset_existing,
        )
        return component_event_id, delta_event_id

    def enqueue(
        self,
        *,
        program_id: UUID | str,
        target: str,
        source_type: str,
        source_id: UUID | str | None,
        filters_json: Mapping[str, Any],
        reset_existing: bool = False,
    ) -> UUID:
        if not target.strip():
            raise ValueError("target must not be empty")
        if not source_type.strip():
            raise ValueError("source_type must not be empty")
        row = self._fetchone(
            _search_projection_event_insert_statement(reset_existing=reset_existing),
            search_projection_event_insert_values(
                program_id=program_id,
                target=target,
                source_type=source_type,
                source_id=source_id,
                filters_json=filters_json,
                dedupe_key=_search_projection_dedupe_key(
                    program_id=program_id,
                    target=target,
                    source_type=source_type,
                    source_id=source_id,
                    filters=filters_json,
                ),
            ),
        )
        if row is None:
            self._connection.rollback()
            raise RuntimeError("search_projection_events insert did not return an id")
        self._connection.commit()
        return UUID(str(row["id"]))

    def _fetchone(self, query: str, parameters: dict[str, object]) -> Mapping[str, Any] | None:
        cursor = self._cursor()
        parameters = _adapt_json_parameters_for_cursor(cursor, parameters)
        try:
            cursor.execute(query, parameters)
            return cursor.fetchone()
        except Exception:
            self._connection.rollback()
            raise

    def _cursor(self) -> SurfaceAnalysisEventCursor:
        return cursor_for(self._connection)


class SurfaceComponentAnalysisEventWorker:
    def __init__(
        self,
        *,
        event_store: SurfaceComponentAnalysisEventStore,
        analysis_store: SurfaceComponentAnalysisStore,
        report_reader: SurfaceComponentReportReader,
        worker_id: str,
        lock_seconds: int,
        max_attempts: int,
        search_event_publisher: SearchProjectionEventPublisher | None = None,
    ) -> None:
        self._event_store = event_store
        self._analysis_store = analysis_store
        self._report_reader = report_reader
        self._worker_id = worker_id
        self._lock_seconds = lock_seconds
        self._max_attempts = max_attempts
        self._search_event_publisher = search_event_publisher

    def process_one(self, *, program_id: UUID | str | None = None) -> SurfaceComponentAnalysisEventProcessResult:
        claimed = self._event_store.claim_next(
            worker_id=self._worker_id,
            lock_seconds=self._lock_seconds,
            max_attempts=self._max_attempts,
            program_id=program_id,
        )
        if claimed is None:
            return SurfaceComponentAnalysisEventProcessResult(status="empty")
        event = claimed.event
        try:
            settings = event.settings_json
            report = self._report_reader.read(
                program_id=event.program_id,
                snapshot_id=event.snapshot_id,
                previous_snapshot_id=event.previous_snapshot_id,
                limit=_int_setting(settings, "limit", 10),
                include_action_candidates=bool(settings.get("include_action_candidates", True)),
                candidate_limit=_int_setting(settings, "candidate_limit", 10),
                component_limit=_int_setting(settings, "component_limit", 10),
                similarity_cutoff=_float_setting(settings, "similarity_cutoff", 0.03),
            )
            materialization = self._analysis_store.materialize(
                report,
                settings_json=settings,
                algorithm_version=event.analysis_version,
            )
            if self._search_event_publisher is not None:
                self._search_event_publisher.enqueue_surface_component_outputs(
                    program_id=materialization.program_id,
                    analysis_run_id=materialization.analysis_run_id,
                    snapshot_id=materialization.snapshot_id,
                )
        except Exception as exc:
            dead = claimed.attempts >= self._max_attempts
            status = "dead" if dead else "failed"
            error = str(exc)
            self._event_store.mark_failed(event.id, error=error, dead=dead, worker_id=self._worker_id)
            return SurfaceComponentAnalysisEventProcessResult(status=status, event_id=event.id, error=error)
        self._event_store.mark_processed(event.id, materialization=materialization, worker_id=self._worker_id)
        return SurfaceComponentAnalysisEventProcessResult(
            status="processed",
            event_id=event.id,
            materialization=materialization,
        )

    def process_loop(
        self,
        *,
        program_id: UUID | str | None = None,
        max_events: int | None = None,
        idle_exit_after: int | None = None,
        poll_seconds: float = 1.0,
        sleep: Callable[[float], object] = default_sleep,
    ) -> SurfaceComponentAnalysisEventLoopResult:
        if max_events is not None and max_events <= 0:
            raise ValueError("max_events must be positive when provided")
        if idle_exit_after is not None and idle_exit_after <= 0:
            raise ValueError("idle_exit_after must be positive when provided")
        if poll_seconds < 0:
            raise ValueError("poll_seconds must not be negative")

        processed = failed = dead = empty = iterations = 0
        consecutive_empty = 0
        last_status: str | None = None
        processed_events = 0
        while max_events is None or processed_events < max_events:
            result = self.process_one(program_id=program_id)
            iterations += 1
            last_status = result.status
            if result.status == "processed":
                processed += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "failed":
                failed += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "dead":
                dead += 1
                processed_events += 1
                consecutive_empty = 0
            elif result.status == "empty":
                empty += 1
                consecutive_empty += 1
                if idle_exit_after is not None and consecutive_empty >= idle_exit_after:
                    break
                if poll_seconds > 0:
                    sleep(poll_seconds)
            else:  # pragma: no cover
                raise RuntimeError(f"unknown surface analysis event status: {result.status}")
        return SurfaceComponentAnalysisEventLoopResult(
            processed=processed,
            failed=failed,
            dead=dead,
            empty=empty,
            iterations=iterations,
            last_status=last_status,
        )


def enqueue_surface_analysis_events_from_batch(
    store: SurfaceComponentAnalysisEventStore,
    *,
    batch: Any,
    settings_json: Mapping[str, Any] | None = None,
) -> int:
    if getattr(batch, "produced_by", None) != "surface-map":
        return 0
    enqueued = 0
    for snapshot_id in _surface_snapshot_ids_from_batch(batch):
        store.enqueue_surface_map_projected(
            program_id=batch.program_id,
            snapshot_id=snapshot_id,
            settings_json=settings_json,
        )
        enqueued += 1
    return enqueued


def _surface_snapshot_ids_from_batch(batch: Any) -> tuple[str, ...]:
    snapshot_ids: list[str] = []
    seen: set[str] = set()
    for fact in getattr(batch, "facts", ()):
        if getattr(fact, "kind", None) != "SurfaceSnapshot":
            continue
        snapshot_id = str(getattr(fact, "key"))
        if snapshot_id in seen:
            continue
        seen.add(snapshot_id)
        snapshot_ids.append(snapshot_id)
    return tuple(snapshot_ids)


def _dedupe_key(*, program_id: UUID | str, snapshot_id: UUID | str, event_type: str, analysis_version: str) -> str:
    return f"surface-component-analysis:{program_id}:{snapshot_id}:{event_type}:{analysis_version}"


def _search_projection_dedupe_key(
    *,
    program_id: UUID | str,
    target: str,
    source_type: str,
    source_id: UUID | str | None,
    filters: Mapping[str, Any],
) -> str:
    filter_items = ",".join(f"{key}={filters[key]}" for key in sorted(filters))
    return f"search-projection:{program_id}:{target}:{source_type}:{source_id or 'none'}:{filter_items}"


def _int_setting(settings: Mapping[str, Any], key: str, default: int) -> int:
    value = settings.get(key, default)
    if value is None:
        return default
    return int(value)


def _float_setting(settings: Mapping[str, Any], key: str, default: float) -> float:
    value = settings.get(key, default)
    if value is None:
        return default
    return float(value)


def _adapt_json_parameters_for_cursor(cursor: SurfaceAnalysisEventCursor, parameters: dict[str, object]) -> dict[str, object]:
    return adapt_surface_analysis_event_json_parameters(cursor, parameters)


__all__ = [
    "ClaimedSurfaceComponentAnalysisEvent",
    "SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING_SQL",
    "SEARCH_PROJECTION_EVENT_INSERT_RESET_SQL",
    "SURFACE_ANALYSIS_EVENT_INSERT_KEEP_EXISTING_SQL",
    "SURFACE_ANALYSIS_EVENT_INSERT_RESET_SQL",
    "SURFACE_COMPONENT_ANALYSIS_EVENT_TYPE",
    "SURFACE_COMPONENT_ANALYSIS_VERSION",
    "SearchProjectionEventPublisher",
    "SurfaceAnalysisEventConnection",
    "SurfaceAnalysisEventCursor",
    "SurfaceComponentAnalysisEvent",
    "SurfaceComponentAnalysisEventLoopResult",
    "SurfaceComponentAnalysisEventProcessResult",
    "SurfaceComponentAnalysisEventStore",
    "SurfaceComponentAnalysisEventWorker",
    "enqueue_surface_analysis_events_from_batch",
    "_search_projection_event_insert_statement",
    "_surface_analysis_event_insert_statement",
]
