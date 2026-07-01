"""SQL query builders for action outcome persistence."""
from __future__ import annotations

import uuid

from sqlalchemy import desc, distinct, func, select

from api.infrastructure.adapters.orm import (
    action_outcomes,
    endpoints,
    http_observations,
    javascript_references,
    jobs,
    raw_artifacts,
    runs,
)


def run_context_query(run_id: uuid.UUID):
    return (
        select(
            action_outcomes.c.id.label("outcome_id"),
            runs.c.id.label("run_id"),
            runs.c.job_id,
            runs.c.program_id,
            runs.c.node_id,
            runs.c.event_name,
            runs.c.status,
            runs.c.terminal_outcome,
            runs.c.attempt,
            runs.c.target_count,
            runs.c.run_payload,
            runs.c.started_at,
            runs.c.finished_at,
            runs.c.error,
            jobs.c.action_id,
            jobs.c.campaign_id,
            jobs.c.capability_id,
            jobs.c.profile_id,
            jobs.c.correlation_id,
        )
        .select_from(
            runs.join(jobs, runs.c.job_id == jobs.c.id).outerjoin(
                action_outcomes,
                action_outcomes.c.run_id == runs.c.id,
            )
        )
        .where(runs.c.id == run_id)
    )


def raw_artifact_stats_query(run_id: uuid.UUID):
    return select(
        func.count(raw_artifacts.c.id).label("count"),
        func.coalesce(func.sum(raw_artifacts.c.size_bytes), 0).label("bytes"),
    ).where(raw_artifacts.c.run_id == run_id)


def http_observation_stats_query(run_id: uuid.UUID):
    return select(
        func.count(http_observations.c.id).label("count"),
        func.count(distinct(http_observations.c.endpoint_id)).label("endpoints"),
        func.count(distinct(http_observations.c.service_id)).label("services"),
    ).where(http_observations.c.run_id == run_id)


def javascript_reference_stats_query(run_id: uuid.UUID):
    return select(
        func.count(javascript_references.c.id).label("count"),
        func.count(distinct(javascript_references.c.endpoint_id)).label("endpoints"),
        func.count(distinct(javascript_references.c.service_id)).label("services"),
    ).where(javascript_references.c.run_id == run_id)


def observed_host_count_query(run_id: uuid.UUID):
    http_hosts = (
        select(endpoints.c.host_id.label("host_id"))
        .select_from(http_observations.join(endpoints, http_observations.c.endpoint_id == endpoints.c.id))
        .where(http_observations.c.run_id == run_id)
    )
    js_hosts = (
        select(endpoints.c.host_id.label("host_id"))
        .select_from(javascript_references.join(endpoints, javascript_references.c.endpoint_id == endpoints.c.id))
        .where(javascript_references.c.run_id == run_id)
    )
    host_ids = http_hosts.union_all(js_hosts).subquery()
    return select(func.count(distinct(host_ids.c.host_id)))


def feedback_target_query(*, action_id: uuid.UUID, run_id: uuid.UUID | None):
    query = (
        select(
            action_outcomes.c.id.label("outcome_id"),
            action_outcomes.c.program_id,
            action_outcomes.c.campaign_id,
            action_outcomes.c.action_id,
            action_outcomes.c.job_id,
            action_outcomes.c.run_id,
        )
        .where(action_outcomes.c.action_id == action_id)
        .order_by(
            desc(action_outcomes.c.finished_at),
            desc(action_outcomes.c.created_at),
            desc(action_outcomes.c.id),
        )
        .limit(1)
    )
    if run_id is not None:
        query = query.where(action_outcomes.c.run_id == run_id)
    return query


def action_outcome_by_id_query(outcome_id: uuid.UUID):
    return select(action_outcomes).where(action_outcomes.c.id == outcome_id)
