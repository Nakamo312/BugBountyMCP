"""Session boundary for action read projections."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionArtifactReference,
    ActionEventRecord,
    ActionRecord,
    ActionRunResult,
)
from api.infrastructure.orchestration.action_read_mappers import (
    action_artifact_reference_from_row,
    action_event_record_from_row,
    action_record_from_row,
    action_run_result_from_row,
)
from api.infrastructure.orchestration.action_read_queries import (
    get_action_query,
    list_action_artifacts_query,
    list_action_events_query,
    list_action_runs_query,
    list_actions_query,
)


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
        async with self.session_factory() as session:
            result = await session.execute(
                list_actions_query(
                    status=status,
                    program_id=program_id,
                    limit=limit,
                    offset=offset,
                )
            )
            rows = result.mappings().all()
        return [action_record_from_row(row) for row in rows]

    async def get_action(self, action_id: uuid.UUID) -> ActionRecord | None:
        async with self.session_factory() as session:
            result = await session.execute(get_action_query(action_id))
            row = result.mappings().one_or_none()
        return None if row is None else action_record_from_row(row)

    async def list_action_events(
        self,
        action_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        async with self.session_factory() as session:
            result = await session.execute(
                list_action_events_query(action_id, limit=limit, offset=offset)
            )
            rows = result.mappings().all()
        return [action_event_record_from_row(row) for row in rows]

    async def list_action_runs(self, action_id: uuid.UUID) -> list[ActionRunResult]:
        async with self.session_factory() as session:
            result = await session.execute(list_action_runs_query(action_id))
            rows = result.mappings().all()
        return [action_run_result_from_row(row) for row in rows]

    async def list_action_artifacts(self, action_id: uuid.UUID) -> list[ActionArtifactReference]:
        async with self.session_factory() as session:
            result = await session.execute(list_action_artifacts_query(action_id))
            rows = result.mappings().all()
        return [action_artifact_reference_from_row(row) for row in rows]
