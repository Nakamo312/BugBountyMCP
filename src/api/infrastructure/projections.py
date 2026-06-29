"""PostgreSQL reader for durable projection lag state."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, tuple_

from api.application.projections import ProjectionKey, ProjectionLagState
from api.infrastructure.adapters.orm import projection_watermarks


class ProjectionStateStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def list_states(
        self,
        *,
        program_id: Any,
        required: Sequence[ProjectionKey],
    ) -> list[ProjectionLagState]:
        requested = tuple(
            (key.projection_type, key.projection_name)
            for key in required
        )
        if not requested:
            return []

        query = select(
            projection_watermarks.c.projection_type,
            projection_watermarks.c.projection_name,
            projection_watermarks.c.status,
            projection_watermarks.c.source_watermark,
            projection_watermarks.c.applied_watermark,
            projection_watermarks.c.lag_count,
        ).where(
            projection_watermarks.c.program_id == program_id,
            tuple_(
                projection_watermarks.c.projection_type,
                projection_watermarks.c.projection_name,
            ).in_(requested),
        )

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()

        return [
            ProjectionLagState(
                key=ProjectionKey(row["projection_type"], row["projection_name"]),
                status=row["status"],
                source_watermark=row["source_watermark"],
                applied_watermark=row["applied_watermark"],
                lag_count=int(row["lag_count"]),
            )
            for row in rows
        ]
