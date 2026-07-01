"""Row mappers for action read projections."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from api.application.action_invocation_payload import action_invocation_value
from api.application.contracts import (
    ActionArtifactReference,
    ActionEventRecord,
    ActionKind,
    ActionRecord,
    ActionRequest,
    ActionRunResult,
    ActionStatus,
    ExecutionStatus,
    TerminalOutcome,
)


def action_record_from_row(row: Mapping[str, Any]) -> ActionRecord:
    request = ActionRequest.model_validate(row["request"])
    return ActionRecord(
        action_id=row["id"],
        program_id=row["program_id"],
        kind=ActionKind(row["kind"]),
        capability_id=row["capability_id"],
        profile_id=row["profile_id"],
        requested_by=row["requested_by"],
        status=ActionStatus(row["status"]),
        targets=request.targets,
        options=request.options,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def action_event_record_from_row(row: Mapping[str, Any]) -> ActionEventRecord:
    payload = dict(row.get("payload") or {})
    action_id_value = action_invocation_value(payload, "action_id")
    return ActionEventRecord(
        event_id=row["event_id"],
        action_id=uuid.UUID(str(action_id_value)) if action_id_value else None,
        event_type=row["event_type"],
        program_id=row["program_id"],
        job_id=row.get("job_id"),
        run_id=row.get("run_id"),
        correlation_id=row["correlation_id"],
        causation_id=row.get("causation_id"),
        source=row["source"],
        profile=row.get("profile"),
        confidence=float(row["confidence"]),
        payload=payload,
        created_at=row["created_at"],
    )


def action_run_result_from_row(row: Mapping[str, Any]) -> ActionRunResult:
    terminal_outcome = (
        TerminalOutcome(row["terminal_outcome"])
        if row.get("terminal_outcome") is not None
        else None
    )
    return ActionRunResult(
        run_id=row["id"],
        job_id=row["job_id"],
        status=ExecutionStatus(row["status"]),
        terminal_outcome=terminal_outcome,
        attempt=row["attempt"],
        error=row.get("error"),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
    )


def action_artifact_reference_from_row(row: Mapping[str, Any]) -> ActionArtifactReference:
    return ActionArtifactReference(
        artifact_id=row["id"],
        job_id=row.get("job_id"),
        run_id=row.get("run_id"),
        artifact_type=row["artifact_type"],
        storage_uri=row["storage_uri"],
        sha256=row["sha256"],
        size_bytes=row["size_bytes"],
        storage_size_bytes=row.get("storage_size_bytes", row["size_bytes"]),
        content_encoding=row.get("content_encoding", "identity"),
        retention_class=row.get("retention_class", "program_lifetime"),
        created_at=row["created_at"],
    )
