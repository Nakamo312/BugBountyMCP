"""Agent wait-condition persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from api.application.agent_wait_conditions import AgentWaitConditionRecord
from api.infrastructure.adapters.orm import agent_wait_conditions, agent_workflow_runs


class AgentWaitConditionStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def list_pending(
        self,
        *,
        limit: int,
        now: datetime,
    ) -> list[AgentWaitConditionRecord]:
        query = (
            self._record_query()
            .where(agent_wait_conditions.c.status == "pending")
            .order_by(agent_wait_conditions.c.created_at.asc())
            .limit(max(1, limit))
        )

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()

        return [self._record_from_row(row) for row in rows]

    async def list_resume_ready(
        self,
        *,
        limit: int,
    ) -> list[AgentWaitConditionRecord]:
        pending_waits = agent_wait_conditions.alias("pending_waits")
        pending_exists = (
            select(pending_waits.c.id)
            .where(
                pending_waits.c.workflow_run_id
                == agent_wait_conditions.c.workflow_run_id,
                pending_waits.c.status == "pending",
            )
            .exists()
        )
        query = (
            self._record_query()
            .select_from(
                agent_wait_conditions.join(
                    agent_workflow_runs,
                    agent_wait_conditions.c.workflow_run_id
                    == agent_workflow_runs.c.id,
                )
            )
            .where(
                agent_wait_conditions.c.status == "resolved",
                agent_workflow_runs.c.status == "waiting",
                ~pending_exists,
            )
            .distinct(agent_wait_conditions.c.workflow_run_id)
            .order_by(
                agent_wait_conditions.c.workflow_run_id,
                agent_wait_conditions.c.resolved_at.desc(),
            )
            .limit(max(1, limit))
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self._record_from_row(row) for row in rows]

    async def mark_resolved(
        self,
        *,
        condition_id: UUID,
        payload: dict[str, Any],
    ) -> bool:
        return await self._mark_terminal(
            condition_id=condition_id,
            status="resolved",
            payload=payload,
        )

    async def mark_timed_out(
        self,
        *,
        condition_id: UUID,
        payload: dict[str, Any],
    ) -> bool:
        return await self._mark_terminal(
            condition_id=condition_id,
            status="timed_out",
            payload=payload,
        )

    async def mark_cancelled(
        self,
        *,
        condition_id: UUID,
        payload: dict[str, Any],
    ) -> bool:
        return await self._mark_terminal(
            condition_id=condition_id,
            status="cancelled",
            payload=payload,
        )

    async def _mark_terminal(
        self,
        *,
        condition_id: UUID,
        status: str,
        payload: dict[str, Any],
    ) -> bool:
        now = datetime.now(timezone.utc)
        statement = (
            update(agent_wait_conditions)
            .where(
                agent_wait_conditions.c.id == condition_id,
                agent_wait_conditions.c.status == "pending",
            )
            .values(
                status=status,
                resolved_payload=payload,
                resolved_at=now,
                updated_at=now,
            )
        )
        async with self.session_factory() as session:
            result = await session.execute(statement)
            await session.commit()
        return bool(result.rowcount)

    @staticmethod
    def _record_query():
        return select(
            agent_wait_conditions.c.id,
            agent_wait_conditions.c.condition_key,
            agent_wait_conditions.c.condition_type,
            agent_wait_conditions.c.program_id,
            agent_wait_conditions.c.workflow_run_id,
            agent_wait_conditions.c.required_state,
            agent_wait_conditions.c.deadline_at,
        )

    @staticmethod
    def _record_from_row(row) -> AgentWaitConditionRecord:
        return AgentWaitConditionRecord(
            condition_id=row["id"],
            condition_key=row["condition_key"],
            condition_type=row["condition_type"],
            program_id=row["program_id"],
            workflow_run_id=row["workflow_run_id"],
            required_state=dict(row["required_state"] or {}),
            deadline_at=row["deadline_at"],
        )


__all__ = ["AgentWaitConditionStore"]
