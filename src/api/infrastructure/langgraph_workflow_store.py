"""LangGraph workflow persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import insert as sa_insert, select, update

from api.application.langgraph_workflows import (
    LangGraphWorkflowState,
    WorkflowStartRequest,
)
from api.infrastructure.adapters.orm import agent_workflow_runs, agent_workflows


class LangGraphWorkflowStore:
    """PostgreSQL-backed skeleton store for LangGraph workflow runs."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def start_run(self, request: WorkflowStartRequest) -> LangGraphWorkflowState:
        workflow_id = uuid4()
        run_id = uuid4()
        correlation_id = uuid4()
        now = datetime.now(timezone.utc)
        metadata = {
            "action_ids": [],
            "wait_condition_ids": [],
            "result_set_keys": [],
        }

        async with self.session_factory() as session:
            await session.execute(
                sa_insert(agent_workflows).values(
                    id=workflow_id,
                    program_id=request.program_id,
                    campaign_id=request.campaign_id,
                    correlation_id=correlation_id,
                    workflow_type=request.workflow_type,
                    status="running",
                    metadata=metadata,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                sa_insert(agent_workflow_runs).values(
                    id=run_id,
                    workflow_id=workflow_id,
                    program_id=request.program_id,
                    campaign_id=request.campaign_id,
                    correlation_id=correlation_id,
                    status="running",
                    current_node=request.entry_node,
                    checkpoint_ref=None,
                    metadata=metadata,
                    created_at=now,
                    updated_at=now,
                    started_at=now,
                )
            )
            result = await session.execute(
                self._state_query().where(agent_workflow_runs.c.id == run_id)
            )
            row = result.mappings().one()
            await session.commit()
        return self._state_from_row(row)

    async def pause_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str,
        current_node: str,
        wait_condition_id: UUID | None,
    ) -> LangGraphWorkflowState:
        now = datetime.now(timezone.utc)
        existing = await self._load_state(run_id)
        wait_ids = [str(item) for item in existing.wait_condition_ids]
        if wait_condition_id is not None and str(wait_condition_id) not in wait_ids:
            wait_ids.append(str(wait_condition_id))
        metadata = {
            "action_ids": [str(item) for item in existing.action_ids],
            "wait_condition_ids": wait_ids,
            "result_set_keys": list(existing.result_set_keys),
        }

        async with self.session_factory() as session:
            await session.execute(
                update(agent_workflow_runs)
                .where(agent_workflow_runs.c.id == run_id)
                .values(
                    status="waiting",
                    current_node=current_node,
                    checkpoint_ref=checkpoint_ref,
                    metadata=metadata,
                    updated_at=now,
                )
            )
            await session.execute(
                update(agent_workflows)
                .where(agent_workflows.c.id == existing.workflow_id)
                .values(status="waiting", metadata=metadata, updated_at=now)
            )
            result = await session.execute(
                self._state_query().where(agent_workflow_runs.c.id == run_id)
            )
            row = result.mappings().one()
            await session.commit()
        return self._state_from_row(row)

    async def resume_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str | None = None,
    ) -> LangGraphWorkflowState:
        now = datetime.now(timezone.utc)
        existing = await self._load_state(run_id)
        values = {
            "status": "running",
            "updated_at": now,
        }
        if checkpoint_ref is not None:
            values["checkpoint_ref"] = checkpoint_ref

        async with self.session_factory() as session:
            await session.execute(
                update(agent_workflow_runs)
                .where(agent_workflow_runs.c.id == run_id)
                .values(**values)
            )
            await session.execute(
                update(agent_workflows)
                .where(agent_workflows.c.id == existing.workflow_id)
                .values(status="running", updated_at=now)
            )
            result = await session.execute(
                self._state_query().where(agent_workflow_runs.c.id == run_id)
            )
            row = result.mappings().one()
            await session.commit()
        return self._state_from_row(row)

    async def cancel_run(
        self,
        *,
        run_id: UUID,
        reason: str | None = None,
    ) -> LangGraphWorkflowState:
        now = datetime.now(timezone.utc)
        existing = await self._load_state(run_id)
        metadata = {
            "action_ids": [str(item) for item in existing.action_ids],
            "wait_condition_ids": [str(item) for item in existing.wait_condition_ids],
            "result_set_keys": list(existing.result_set_keys),
        }
        if reason is not None:
            metadata["terminal_reason"] = reason

        async with self.session_factory() as session:
            await session.execute(
                update(agent_workflow_runs)
                .where(agent_workflow_runs.c.id == run_id)
                .values(
                    status="cancelled",
                    metadata=metadata,
                    finished_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                update(agent_workflows)
                .where(agent_workflows.c.id == existing.workflow_id)
                .values(status="cancelled", metadata=metadata, updated_at=now)
            )
            result = await session.execute(
                self._state_query().where(agent_workflow_runs.c.id == run_id)
            )
            row = result.mappings().one()
            await session.commit()
        return self._state_from_row(row)

    async def _load_state(self, run_id: UUID) -> LangGraphWorkflowState:
        async with self.session_factory() as session:
            result = await session.execute(
                self._state_query().where(agent_workflow_runs.c.id == run_id)
            )
            row = result.mappings().one()
        return self._state_from_row(row)

    @staticmethod
    def _state_query():
        return select(
            agent_workflows.c.id.label("workflow_id"),
            agent_workflow_runs.c.id.label("run_id"),
            agent_workflow_runs.c.program_id,
            agent_workflow_runs.c.campaign_id,
            agent_workflow_runs.c.correlation_id,
            agent_workflows.c.workflow_type,
            agent_workflow_runs.c.status,
            agent_workflow_runs.c.current_node,
            agent_workflow_runs.c.checkpoint_ref,
            agent_workflow_runs.c["metadata"],
        ).select_from(
            agent_workflow_runs.join(
                agent_workflows,
                agent_workflow_runs.c.workflow_id == agent_workflows.c.id,
            )
        )

    @staticmethod
    def _state_from_row(row) -> LangGraphWorkflowState:
        metadata = dict(row["metadata"] or {})
        return LangGraphWorkflowState(
            workflow_id=row["workflow_id"],
            run_id=row["run_id"],
            program_id=row["program_id"],
            campaign_id=row["campaign_id"],
            correlation_id=row["correlation_id"],
            workflow_type=row["workflow_type"],
            status=row["status"],
            current_node=row["current_node"],
            checkpoint_ref=row["checkpoint_ref"],
            action_ids=tuple(UUID(str(item)) for item in metadata.get("action_ids", ())),
            wait_condition_ids=tuple(
                UUID(str(item)) for item in metadata.get("wait_condition_ids", ())
            ),
            result_set_keys=tuple(str(item) for item in metadata.get("result_set_keys", ())),
        )


__all__ = ["LangGraphWorkflowStore"]
