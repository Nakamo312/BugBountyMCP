"""SQL query builders for action read projections."""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from api.application.action_invocation_payload import ACTION_INVOCATION_PAYLOAD_KEY
from api.infrastructure.adapters.orm import action_requests, event_store, jobs, raw_artifacts, runs


def list_actions_query(
    *,
    status: str | None,
    program_id: uuid.UUID | None,
    limit: int,
    offset: int,
):
    query = select(action_requests).order_by(action_requests.c.created_at.desc())
    if status is not None:
        query = query.where(action_requests.c.status == status)
    if program_id is not None:
        query = query.where(action_requests.c.program_id == program_id)
    return query.limit(limit).offset(offset)


def get_action_query(action_id: uuid.UUID):
    return select(action_requests).where(action_requests.c.id == action_id)


def list_action_events_query(action_id: uuid.UUID, *, limit: int, offset: int):
    return (
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
        .where(
            or_(
                event_store.c.payload["action_id"].as_string() == str(action_id),
                event_store.c.payload[ACTION_INVOCATION_PAYLOAD_KEY]["action_id"].as_string()
                == str(action_id),
            )
        )
        .order_by(event_store.c.created_at.asc(), event_store.c.event_id.asc())
        .limit(limit)
        .offset(offset)
    )


def list_action_runs_query(action_id: uuid.UUID):
    return (
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


def list_action_artifacts_query(action_id: uuid.UUID):
    return (
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
