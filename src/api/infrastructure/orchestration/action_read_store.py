"""Read-only action views for orchestration actions, events, runs, and artifacts."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

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
from api.infrastructure.adapters.orm import action_requests, event_store, jobs, raw_artifacts, runs


class ActionReadStore:
    """Read-only action projections for API-facing action views."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def list_actions(
        self,
        *,
        status: str | None = None,
        program_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        query = select(action_requests).order_by(action_requests.c.created_at.desc())
        if status is not None:
            query = query.where(action_requests.c.status == status)
        if program_id is not None:
            query = query.where(action_requests.c.program_id == program_id)
        query = query.limit(limit).offset(offset)

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()

        return [self.action_record_from_row(row) for row in rows]

    async def get_action(self, action_id: uuid.UUID) -> ActionRecord | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(action_requests).where(action_requests.c.id == action_id)
            )
            row = result.mappings().one_or_none()

        if row is None:
            return None
        return self.action_record_from_row(row)

    async def list_action_events(
        self,
        action_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        query = (
            select(
                event_store.c.event_id,
                event_store.c.event_type,
                event_store.c.program_id,
                event_store.c.job_id,
                event_store.c.run_id,
                event_store.c.correlation_id,
                event_store.c.causation_id,
                event_store.c.source,
                event_store.c.profile,
                event_store.c.confidence,
                event_store.c.payload,
                event_store.c.created_at,
            )
            .where(event_store.c.payload["action_id"].as_string() == str(action_id))
            .order_by(event_store.c.created_at.asc(), event_store.c.event_id.asc())
            .limit(limit)
            .offset(offset)
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self.action_event_record_from_row(row) for row in rows]

    async def list_action_runs(self, action_id: uuid.UUID) -> list[ActionRunResult]:
        query = (
            select(
                runs.c.id,
                runs.c.job_id,
                runs.c.status,
                runs.c.terminal_outcome,
                runs.c.attempt,
                runs.c.error,
                runs.c.started_at,
                runs.c.finished_at,
            )
            .select_from(runs.join(jobs, runs.c.job_id == jobs.c.id))
            .where(jobs.c.action_id == action_id)
            .order_by(runs.c.created_at.asc(), runs.c.id.asc())
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self.action_run_result_from_row(row) for row in rows]

    async def list_action_artifacts(self, action_id: uuid.UUID) -> list[ActionArtifactReference]:
        query = (
            select(
                raw_artifacts.c.id,
                raw_artifacts.c.job_id,
                raw_artifacts.c.run_id,
                raw_artifacts.c.artifact_type,
                raw_artifacts.c.storage_uri,
                raw_artifacts.c.sha256,
                raw_artifacts.c.size_bytes,
                raw_artifacts.c.storage_size_bytes,
                raw_artifacts.c.content_encoding,
                raw_artifacts.c.retention_class,
                raw_artifacts.c.created_at,
            )
            .select_from(raw_artifacts.join(jobs, raw_artifacts.c.job_id == jobs.c.id))
            .where(jobs.c.action_id == action_id)
            .order_by(raw_artifacts.c.created_at.asc(), raw_artifacts.c.id.asc())
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self.action_artifact_reference_from_row(row) for row in rows]

    @staticmethod
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

    @staticmethod
    def action_event_record_from_row(row: Mapping[str, Any]) -> ActionEventRecord:
        payload = dict(row.get("payload") or {})
        action_id_value = payload.get("action_id")
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

    @staticmethod
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

    @staticmethod
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
