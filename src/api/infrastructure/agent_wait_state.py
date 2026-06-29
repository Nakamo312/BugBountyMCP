"""PostgreSQL execution state reader for agent wait predicates."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from api.application.agent_wait_conditions import RunWaitState
from api.infrastructure.adapters.orm import runs


class AgentExecutionStateReader:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def get_run_state(
        self,
        *,
        program_id: Any,
        run_id: UUID,
    ) -> RunWaitState | None:
        query = select(
            runs.c.id,
            runs.c.status,
            runs.c.terminal_outcome,
        ).where(
            runs.c.id == run_id,
            runs.c.program_id == program_id,
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return RunWaitState(
            run_id=row["id"],
            status=str(row["status"]),
            terminal_outcome=(
                str(row["terminal_outcome"])
                if row["terminal_outcome"] is not None
                else None
            ),
        )
