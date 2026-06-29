"""Durable pipeline metrics row collection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.orchestration import pipeline_metrics_queries as queries


@dataclass(frozen=True)
class PipelineMetricRows:
    run_rows: list[dict[str, Any]]
    scheduled_state_rows: list[dict[str, Any]]
    scheduled_state_age_rows: list[dict[str, Any]]
    queue_rows: list[dict[str, Any]]
    leased_rows: list[dict[str, Any]]
    dedup_rows: list[dict[str, Any]]
    retry_rows: list[dict[str, Any]]
    reconcile_rows: list[dict[str, Any]]
    duration_rows: list[dict[str, Any]]
    scheduled_age_rows: list[dict[str, Any]]
    leased_age_rows: list[dict[str, Any]]
    retry_age_rows: list[dict[str, Any]]
    reconcile_age_rows: list[dict[str, Any]]
    running_age_rows: list[dict[str, Any]]


async def collect_pipeline_metric_rows(
    session_factory: async_sessionmaker,
    *,
    program_id: UUID | None = None,
) -> PipelineMetricRows:
    async with session_factory() as session:
        return PipelineMetricRows(
            run_rows=await _fetch_rows(session, queries.run_state_query(program_id=program_id)),
            scheduled_state_rows=await _fetch_rows(
                session,
                queries.scheduled_state_query(program_id=program_id),
            ),
            scheduled_state_age_rows=await _fetch_rows(
                session,
                queries.scheduled_state_oldest_age_query(program_id=program_id),
            ),
            queue_rows=await _fetch_rows(
                session,
                queries.scheduled_queue_query(program_id=program_id),
            ),
            leased_rows=await _fetch_rows(
                session,
                queries.scheduled_leased_query(program_id=program_id),
            ),
            dedup_rows=await _fetch_rows(
                session,
                queries.scheduled_work_dedup_query(program_id=program_id),
            ),
            retry_rows=await _fetch_rows(session, queries.retry_due_query(program_id=program_id)),
            reconcile_rows=await _fetch_rows(session, queries.reconcile_query(program_id=program_id)),
            duration_rows=await _fetch_rows(session, queries.duration_query(program_id=program_id)),
            scheduled_age_rows=await _fetch_rows(
                session,
                queries.scheduled_oldest_age_query(program_id=program_id),
            ),
            leased_age_rows=await _fetch_rows(
                session,
                queries.scheduled_leased_oldest_age_query(program_id=program_id),
            ),
            retry_age_rows=await _fetch_rows(
                session,
                queries.retry_due_oldest_age_query(program_id=program_id),
            ),
            reconcile_age_rows=await _fetch_rows(
                session,
                queries.reconcile_oldest_age_query(program_id=program_id),
            ),
            running_age_rows=await _fetch_rows(
                session,
                queries.running_oldest_age_query(program_id=program_id),
            ),
        )


async def _fetch_rows(session: Any, query: Any) -> list[dict[str, Any]]:
    return list((await session.execute(query)).mappings().all())
