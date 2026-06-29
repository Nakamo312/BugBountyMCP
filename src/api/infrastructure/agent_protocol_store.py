"""M6 REST agent protocol persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.adapters.orm import (
    agent_inbox,
    agent_result_sets,
    agent_subscriptions,
    agent_wait_conditions,
    agent_workflow_runs,
)
from api.infrastructure.agent_protocol_inbox_claims import (
    claim_inbox_statement,
    claim_request,
)


class AgentProtocolStore:
    """Narrow durable store for the M6 REST agent protocol."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def create_subscription(
        self,
        *,
        program_id: Any,
        event_type: str,
        inbox_key: str,
        dedupe_key: str,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        workflow_id: Any | None = None,
        workflow_run_id: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        statement = insert(agent_subscriptions).values(
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            program_id=program_id,
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            event_type=event_type,
            inbox_key=inbox_key,
            dedupe_key=dedupe_key,
            status="active",
            metadata=metadata or {},
        )
        statement = statement.on_conflict_do_update(
            index_elements=["dedupe_key"],
            set_={
                "workflow_id": statement.excluded.workflow_id,
                "workflow_run_id": statement.excluded.workflow_run_id,
                "program_id": statement.excluded.program_id,
                "campaign_id": statement.excluded.campaign_id,
                "correlation_id": statement.excluded.correlation_id,
                "event_type": statement.excluded.event_type,
                "inbox_key": statement.excluded.inbox_key,
                "status": "active",
                "metadata": statement.excluded["metadata"],
                "updated_at": datetime.now(timezone.utc),
            },
        ).returning(agent_subscriptions.c.id)

        async with self.session_factory() as session:
            result = await session.execute(statement)
            subscription_id = result.scalar_one_or_none()
            await session.commit()
        return subscription_id

    async def list_inbox(
        self,
        *,
        program_id: Any,
        status: str | None = "pending",
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(agent_inbox).where(agent_inbox.c.program_id == program_id)
        if status is not None:
            query = query.where(agent_inbox.c.status == status)
        if campaign_id is not None:
            query = query.where(agent_inbox.c.campaign_id == campaign_id)
        if correlation_id is not None:
            query = query.where(agent_inbox.c.correlation_id == correlation_id)
        query = query.order_by(agent_inbox.c.available_at.asc()).limit(max(1, limit))

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [dict(row) for row in rows]

    async def claim_inbox(
        self,
        *,
        program_id: Any | None = None,
        consumer_id: str,
        lease_seconds: int = 300,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        inbox_key: str | None = None,
        message_type: str | None = None,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically claim available agent inbox messages for one consumer."""

        request = claim_request(
            program_id=program_id,
            consumer_id=consumer_id,
            lease_seconds=lease_seconds,
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            inbox_key=inbox_key,
            message_type=message_type,
            limit=limit,
            now=now,
        )
        statement = claim_inbox_statement(request)

        async with self.session_factory() as session:
            result = await session.execute(statement)
            rows = result.mappings().all()
            await session.commit()
        return [dict(row) for row in rows]

    async def ack_inbox_message(self, *, message_id: Any) -> None:
        now = datetime.now(timezone.utc)
        statement = (
            update(agent_inbox)
            .where(
                agent_inbox.c.id == message_id,
                agent_inbox.c.status.in_(["pending", "claimed", "failed"]),
            )
            .values(
                status="processed",
                processed_at=now,
                updated_at=now,
                locked_by=None,
                locked_until=None,
            )
        )
        async with self.session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def record_inbox_handoff_error(
        self,
        *,
        message_id: Any,
        error: str,
        now: datetime | None = None,
    ) -> None:
        """Record handoff failure diagnostics without changing lease state."""

        bounded_error = (error or "handoff failed")[:4000]
        now = now or datetime.now(timezone.utc)
        statement = (
            update(agent_inbox)
            .where(
                agent_inbox.c.id == message_id,
                agent_inbox.c.status == "claimed",
            )
            .values(
                last_error=bounded_error,
                updated_at=now,
            )
        )
        async with self.session_factory() as session:
            await session.execute(statement)
            await session.commit()

    async def get_workflow_run_status(self, *, run_id: Any) -> str | None:
        query = select(agent_workflow_runs.c.status).where(
            agent_workflow_runs.c.id == run_id
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
        return result.scalar_one_or_none()

    async def cancel_workflow_run_dependents(
        self,
        *,
        run_id: Any,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Persist cancellation intent around a workflow run."""

        now = now or datetime.now(timezone.utc)
        reason_text = (reason or "workflow cancelled")[:4000]
        inbox_error = f"workflow cancelled: {reason_text}"[:4000]
        payload = {"reason": reason_text}

        subscription_statement = (
            update(agent_subscriptions)
            .where(
                agent_subscriptions.c.workflow_run_id == run_id,
                agent_subscriptions.c.status.in_(["active", "paused"]),
            )
            .values(status="cancelled", updated_at=now)
        )
        inbox_statement = (
            update(agent_inbox)
            .where(
                agent_inbox.c.workflow_run_id == run_id,
                agent_inbox.c.status.in_(["pending", "claimed", "failed"]),
            )
            .values(
                status="cancelled",
                locked_by=None,
                locked_until=None,
                last_error=inbox_error,
                updated_at=now,
            )
        )
        wait_statement = (
            update(agent_wait_conditions)
            .where(
                agent_wait_conditions.c.workflow_run_id == run_id,
                agent_wait_conditions.c.status == "pending",
            )
            .values(
                status="cancelled",
                resolved_payload=payload,
                resolved_at=now,
                updated_at=now,
            )
        )

        async with self.session_factory() as session:
            subscription_result = await session.execute(subscription_statement)
            inbox_result = await session.execute(inbox_statement)
            wait_result = await session.execute(wait_statement)
            await session.commit()

        return {
            "subscriptions_cancelled": max(
                0, int(getattr(subscription_result, "rowcount", 0) or 0)
            ),
            "inbox_messages_cancelled": max(
                0, int(getattr(inbox_result, "rowcount", 0) or 0)
            ),
            "wait_conditions_cancelled": max(
                0, int(getattr(wait_result, "rowcount", 0) or 0)
            ),
        }

    async def create_wait_condition(
        self,
        *,
        workflow_run_id: Any,
        program_id: Any,
        condition_type: str,
        condition_key: str,
        required_state: dict[str, Any],
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        deadline_at: datetime | None = None,
    ) -> Any | None:
        statement = insert(agent_wait_conditions).values(
            workflow_run_id=workflow_run_id,
            program_id=program_id,
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            condition_type=condition_type,
            condition_key=condition_key,
            status="pending",
            required_state=required_state,
            deadline_at=deadline_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["workflow_run_id", "condition_key"],
            set_={
                "required_state": statement.excluded.required_state,
                "deadline_at": statement.excluded.deadline_at,
                "status": "pending",
                "resolved_payload": None,
                "resolved_at": None,
                "updated_at": datetime.now(timezone.utc),
            },
        ).returning(agent_wait_conditions.c.id)

        async with self.session_factory() as session:
            result = await session.execute(statement)
            condition_id = result.scalar_one_or_none()
            await session.commit()
        return condition_id

    async def list_wait_conditions(
        self,
        *,
        program_id: Any,
        status: str | None = None,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(agent_wait_conditions).where(
            agent_wait_conditions.c.program_id == program_id
        )
        if status is not None:
            query = query.where(agent_wait_conditions.c.status == status)
        if campaign_id is not None:
            query = query.where(agent_wait_conditions.c.campaign_id == campaign_id)
        if correlation_id is not None:
            query = query.where(agent_wait_conditions.c.correlation_id == correlation_id)
        query = query.order_by(agent_wait_conditions.c.created_at.asc()).limit(max(1, limit))

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [dict(row) for row in rows]

    async def upsert_result_set(
        self,
        *,
        program_id: Any,
        result_type: str,
        result_key: str,
        payload: dict[str, Any],
        artifact_refs: list[dict[str, Any]],
        fact_refs: list[dict[str, Any]],
        search_refs: list[dict[str, Any]],
        graph_refs: list[dict[str, Any]],
        workflow_id: Any | None = None,
        workflow_run_id: Any | None = None,
        action_id: Any | None = None,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
    ) -> Any | None:
        statement = insert(agent_result_sets).values(
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            action_id=action_id,
            program_id=program_id,
            campaign_id=campaign_id,
            correlation_id=correlation_id,
            result_type=result_type,
            result_key=result_key,
            payload=payload,
            artifact_refs=artifact_refs,
            fact_refs=fact_refs,
            search_refs=search_refs,
            graph_refs=graph_refs,
        )
        statement = statement.on_conflict_do_update(
            index_elements=["program_id", "result_key"],
            set_={
                "workflow_id": statement.excluded.workflow_id,
                "workflow_run_id": statement.excluded.workflow_run_id,
                "action_id": statement.excluded.action_id,
                "campaign_id": statement.excluded.campaign_id,
                "correlation_id": statement.excluded.correlation_id,
                "result_type": statement.excluded.result_type,
                "payload": statement.excluded.payload,
                "artifact_refs": statement.excluded.artifact_refs,
                "fact_refs": statement.excluded.fact_refs,
                "search_refs": statement.excluded.search_refs,
                "graph_refs": statement.excluded.graph_refs,
            },
        ).returning(agent_result_sets.c.id)

        async with self.session_factory() as session:
            result = await session.execute(statement)
            result_set_id = result.scalar_one_or_none()
            await session.commit()
        return result_set_id

    async def list_result_sets(
        self,
        *,
        program_id: Any,
        result_key: str | None = None,
        action_id: Any | None = None,
        campaign_id: Any | None = None,
        workflow_id: Any | None = None,
        workflow_run_id: Any | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = select(agent_result_sets).where(
            agent_result_sets.c.program_id == program_id
        )
        if result_key is not None:
            query = query.where(agent_result_sets.c.result_key == result_key)
        if action_id is not None:
            query = query.where(agent_result_sets.c.action_id == action_id)
        if campaign_id is not None:
            query = query.where(agent_result_sets.c.campaign_id == campaign_id)
        if workflow_id is not None:
            query = query.where(agent_result_sets.c.workflow_id == workflow_id)
        if workflow_run_id is not None:
            query = query.where(agent_result_sets.c.workflow_run_id == workflow_run_id)
        query = query.order_by(agent_result_sets.c.created_at.desc()).limit(max(1, limit))

        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [dict(row) for row in rows]



__all__ = ["AgentProtocolStore"]
