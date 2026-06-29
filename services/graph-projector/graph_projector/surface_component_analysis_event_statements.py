from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from uuid import UUID, uuid4

from .row_codec import adapt_json_parameters_for_cursor, optional_uuid_text as _optional_uuid_text
from .surface_component_analysis_event_models import (
    ClaimedSurfaceComponentAnalysisEvent,
    SurfaceAnalysisEventCursor,
    SurfaceComponentAnalysisEvent,
)
from .surface_component_materialization import SurfaceComponentMaterializationResult

SURFACE_COMPONENT_ANALYSIS_EVENT_TYPE = "surface_map_projected"
SURFACE_COMPONENT_ANALYSIS_VERSION = "surface-component-analysis-v1"

SURFACE_ANALYSIS_EVENT_JSON_KEYS = frozenset({"settings_json", "result_json"})

SURFACE_ANALYSIS_EVENT_INSERT_RESET_SQL = """
INSERT INTO surface_component_analysis_events (
    id,
    program_id,
    snapshot_id,
    previous_snapshot_id,
    event_type,
    analysis_version,
    dedupe_key,
    settings_json
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(snapshot_id)s,
    %(previous_snapshot_id)s,
    %(event_type)s,
    %(analysis_version)s,
    %(dedupe_key)s,
    %(settings_json)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET previous_snapshot_id = EXCLUDED.previous_snapshot_id,
    settings_json = EXCLUDED.settings_json,
    status = 'pending',
    attempts = 0,
    available_at = now(),
    locked_by = NULL,
    locked_until = NULL,
    processed_at = NULL,
    last_error = NULL,
    updated_at = now()
RETURNING id;
""".strip()

SURFACE_ANALYSIS_EVENT_INSERT_KEEP_EXISTING_SQL = """
INSERT INTO surface_component_analysis_events (
    id,
    program_id,
    snapshot_id,
    previous_snapshot_id,
    event_type,
    analysis_version,
    dedupe_key,
    settings_json
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(snapshot_id)s,
    %(previous_snapshot_id)s,
    %(event_type)s,
    %(analysis_version)s,
    %(dedupe_key)s,
    %(settings_json)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET updated_at = surface_component_analysis_events.updated_at
RETURNING id;
""".strip()

SURFACE_ANALYSIS_EVENT_CLAIM_NEXT_SQL = """
WITH next_event AS (
    SELECT id
    FROM surface_component_analysis_events
    WHERE status IN ('pending', 'failed')
      AND available_at <= %(now)s
      AND attempts < %(max_attempts)s
      AND (%(program_id)s IS NULL OR program_id = %(program_id)s)
      AND (locked_until IS NULL OR locked_until < %(now)s)
    ORDER BY available_at ASC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE surface_component_analysis_events
SET status = 'locked',
    locked_by = %(worker_id)s,
    locked_until = %(locked_until)s,
    attempts = attempts + 1,
    last_error = NULL,
    updated_at = %(now)s
WHERE id = (SELECT id FROM next_event)
RETURNING id,
          program_id,
          snapshot_id,
          previous_snapshot_id,
          event_type,
          analysis_version,
          settings_json,
          attempts;
""".strip()

SURFACE_ANALYSIS_EVENT_MARK_PROCESSED_SQL = """
UPDATE surface_component_analysis_events
SET status = 'processed',
    processed_at = %(now)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = NULL,
    result_json = %(result_json)s
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip()

SURFACE_ANALYSIS_EVENT_MARK_FAILED_SQL = """
UPDATE surface_component_analysis_events
SET status = %(status)s,
    updated_at = %(now)s,
    locked_by = NULL,
    locked_until = NULL,
    last_error = %(error)s
WHERE id = %(event_id)s
  AND status = 'locked'
  AND locked_by = %(worker_id)s;
""".strip()

SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_DELTA_SQL = """
SELECT from_snapshot_id
FROM surface_deltas
WHERE program_id = %(program_id)s
  AND to_snapshot_id = %(snapshot_id)s
  AND from_snapshot_id IS NOT NULL
ORDER BY created_at ASC
LIMIT 1;
""".strip()

SURFACE_ANALYSIS_PREVIOUS_SNAPSHOT_FROM_SNAPSHOT_SQL = """
SELECT previous.id
FROM surface_snapshots current_snapshot
JOIN surface_snapshots previous
  ON previous.program_id = current_snapshot.program_id
 AND previous.created_at < current_snapshot.created_at
WHERE current_snapshot.program_id = %(program_id)s
  AND current_snapshot.id = %(snapshot_id)s
ORDER BY previous.created_at DESC
LIMIT 1;
""".strip()

SEARCH_PROJECTION_EVENT_INSERT_RESET_SQL = """
INSERT INTO search_projection_events (
    id,
    program_id,
    target,
    source_type,
    source_id,
    filters_json,
    dedupe_key
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(target)s,
    %(source_type)s,
    %(source_id)s,
    %(filters_json)s,
    %(dedupe_key)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET filters_json = EXCLUDED.filters_json,
    status = 'pending',
    attempts = 0,
    available_at = now(),
    locked_by = NULL,
    locked_until = NULL,
    processed_at = NULL,
    last_error = NULL,
    result_json = '{}'::jsonb,
    updated_at = now()
RETURNING id;
""".strip()

SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING_SQL = """
INSERT INTO search_projection_events (
    id,
    program_id,
    target,
    source_type,
    source_id,
    filters_json,
    dedupe_key
)
VALUES (
    %(id)s,
    %(program_id)s,
    %(target)s,
    %(source_type)s,
    %(source_id)s,
    %(filters_json)s,
    %(dedupe_key)s
)
ON CONFLICT (dedupe_key) DO UPDATE
SET updated_at = search_projection_events.updated_at
RETURNING id;
""".strip()


def surface_analysis_event_insert_statement(*, reset_existing: bool) -> str:
    return SURFACE_ANALYSIS_EVENT_INSERT_RESET_SQL if reset_existing else SURFACE_ANALYSIS_EVENT_INSERT_KEEP_EXISTING_SQL


def search_projection_event_insert_statement(*, reset_existing: bool) -> str:
    return SEARCH_PROJECTION_EVENT_INSERT_RESET_SQL if reset_existing else SEARCH_PROJECTION_EVENT_INSERT_KEEP_EXISTING_SQL


def surface_analysis_event_insert_values(
    *,
    program_id: UUID | str,
    snapshot_id: UUID | str,
    previous_snapshot_id: UUID | str | None,
    event_type: str,
    analysis_version: str,
    settings_json: Mapping[str, Any] | None,
    dedupe_key: str,
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "program_id": str(program_id),
        "snapshot_id": str(snapshot_id),
        "previous_snapshot_id": _optional_uuid_text(previous_snapshot_id),
        "event_type": event_type.strip(),
        "analysis_version": analysis_version.strip(),
        "dedupe_key": dedupe_key,
        "settings_json": dict(settings_json or {}),
    }


def claim_next_surface_analysis_event_values(
    *,
    worker_id: str,
    lock_seconds: int,
    max_attempts: int,
    program_id: UUID | str | None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "worker_id": worker_id,
        "now": now,
        "locked_until": now + timedelta(seconds=lock_seconds),
        "max_attempts": max_attempts,
        "program_id": _optional_uuid_text(program_id),
    }


def mark_processed_surface_analysis_event_values(
    *,
    event_id: UUID,
    materialization: SurfaceComponentMaterializationResult,
    worker_id: str,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {"event_id": event_id, "now": now, "result_json": materialization.to_dict(), "worker_id": worker_id}


def mark_failed_surface_analysis_event_values(
    *,
    event_id: UUID,
    error: str,
    dead: bool,
    worker_id: str,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "status": "dead" if dead else "failed",
        "now": datetime.now(UTC),
        "error": error[:4000],
        "worker_id": worker_id,
    }


def previous_snapshot_values(*, program_id: UUID | str, snapshot_id: UUID | str) -> dict[str, object]:
    return {"program_id": str(program_id), "snapshot_id": str(snapshot_id)}


def search_projection_event_insert_values(
    *,
    program_id: UUID | str,
    target: str,
    source_type: str,
    source_id: UUID | str | None,
    filters_json: Mapping[str, Any],
    dedupe_key: str,
) -> dict[str, object]:
    return {
        "id": str(uuid4()),
        "program_id": str(program_id),
        "target": target.strip(),
        "source_type": source_type.strip(),
        "source_id": None if source_id is None else str(source_id),
        "filters_json": dict(filters_json),
        "dedupe_key": dedupe_key,
    }


def claimed_surface_analysis_event_from_row(row: Mapping[str, Any]) -> ClaimedSurfaceComponentAnalysisEvent:
    attempts = int(row["attempts"])
    event = SurfaceComponentAnalysisEvent(
        id=UUID(str(row["id"])),
        program_id=str(row["program_id"]),
        snapshot_id=str(row["snapshot_id"]),
        previous_snapshot_id=None if row.get("previous_snapshot_id") is None else str(row["previous_snapshot_id"]),
        event_type=str(row["event_type"]),
        analysis_version=str(row["analysis_version"]),
        settings_json=dict(row.get("settings_json") or {}),
        attempts=attempts,
    )
    return ClaimedSurfaceComponentAnalysisEvent(event=event, attempts=attempts)


def adapt_surface_analysis_event_json_parameters(
    cursor: SurfaceAnalysisEventCursor,
    parameters: dict[str, object],
) -> dict[str, object]:
    return adapt_json_parameters_for_cursor(cursor, parameters, json_keys=SURFACE_ANALYSIS_EVENT_JSON_KEYS)
