from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import (
    optional_uuid,
    required_row_text,
    required_row_uuid,
)


@dataclass(frozen=True)
class RawArtifactProjectionRow:
    program_id: UUID
    artifact_id: UUID
    run_id: UUID
    job_id: UUID | None
    node_id: str
    event_name: str
    artifact_type: str
    storage_uri: str
    sha256: str
    size_bytes: int
    created_at: str | None


def parse_raw_artifact_row(row: Mapping[str, Any]) -> RawArtifactProjectionRow | None:
    run_id = optional_uuid(row.get("run_id"))
    if run_id is None:
        return None
    return RawArtifactProjectionRow(
        program_id=required_row_uuid(row, "program_id", context="raw artifact row"),
        artifact_id=required_row_uuid(row, "id", context="raw artifact row"),
        run_id=run_id,
        job_id=optional_uuid(row.get("job_id")),
        node_id=required_row_text(row, "node_id", context="raw artifact row"),
        event_name=required_row_text(row, "event_name", context="raw artifact row"),
        artifact_type=required_row_text(row, "artifact_type", context="raw artifact row"),
        storage_uri=required_row_text(row, "storage_uri", context="raw artifact row"),
        sha256=required_row_text(row, "sha256", context="raw artifact row"),
        size_bytes=int(row.get("size_bytes") or 0),
        created_at=_optional_datetime(row.get("created_at")),
    )


def _optional_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None
