"""Measured run telemetry for action outcome memory."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from api.application.contracts import ActionOutcomeMeasures
from api.infrastructure.action_outcome_mappers import duration_ms
from api.infrastructure.action_outcome_queries import (
    http_observation_stats_query,
    javascript_reference_stats_query,
    observed_host_count_query,
    raw_artifact_stats_query,
)


async def collect_action_outcome_measures(
    session,
    *,
    run_id: uuid.UUID,
    row: Mapping[str, Any],
) -> ActionOutcomeMeasures:
    raw_stats = (await session.execute(raw_artifact_stats_query(run_id))).mappings().one()
    http_stats = (await session.execute(http_observation_stats_query(run_id))).mappings().one()
    js_stats = (await session.execute(javascript_reference_stats_query(run_id))).mappings().one()
    host_count = await observed_host_count(session, run_id=run_id)
    return ActionOutcomeMeasures(
        raw_artifact_count=int(raw_stats["count"] or 0),
        raw_artifact_bytes=int(raw_stats["bytes"] or 0),
        observed_hosts_count=host_count,
        observed_services_count=max(
            int(http_stats["services"] or 0),
            int(js_stats["services"] or 0),
        ),
        observed_endpoints_count=max(
            int(http_stats["endpoints"] or 0),
            int(js_stats["endpoints"] or 0),
        ),
        http_observation_count=int(http_stats["count"] or 0),
        javascript_reference_count=int(js_stats["count"] or 0),
        duration_ms=duration_ms(row.get("started_at"), row.get("finished_at")),
        error_count=1 if row.get("error") else 0,
    )


async def observed_host_count(session, *, run_id: uuid.UUID) -> int:
    result = await session.execute(observed_host_count_query(run_id))
    return int(result.scalar_one() or 0)
