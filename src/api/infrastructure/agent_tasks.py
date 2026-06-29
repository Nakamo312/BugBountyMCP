"""Postgres store for user-facing agent tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert as sa_insert, select
from sqlalchemy.dialects.postgresql import insert

from api.application.agent_tasks import (
    AGENT_TASK_FOLLOWUP_SCHEMA_VERSION,
    AGENT_TASK_PROMPT_MESSAGE_TYPE,
    AgentTaskAgentReplyRequest,
    AgentTaskCreated,
    AgentTaskFollowupRequest,
    AgentTaskMessageKind,
    AgentTaskMessageRecord,
    AgentTaskMessageRole,
    AgentTaskPromptRequest,
    AgentTaskRecord,
    AgentTaskStatus,
    body_hash,
)
from api.application.agent_runtime_usage import runtime_usage_delta_from_metadata
from api.infrastructure.adapters.orm import agent_inbox, agent_runtime_usage_daily, agent_task_messages, agent_tasks


class AgentTaskStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def create_prompt_task(
        self,
        *,
        request: AgentTaskPromptRequest,
        task_id: UUID,
        message_id: UUID,
        title: str,
        prompt_excerpt: str,
        prompt_hash: str,
        sanitized_context_refs: list[dict[str, Any]],
        sanitized_metadata: dict[str, Any],
        inbox_payload: dict[str, Any],
        dedupe_key: str,
    ) -> AgentTaskCreated:
        task_values = {
            "id": task_id,
            "program_id": request.program_id,
            "campaign_id": request.campaign_id,
            "correlation_id": request.correlation_id,
            "status": AgentTaskStatus.QUEUED.value,
            "target_agent": request.target_agent,
            "title": title,
            "prompt_excerpt": prompt_excerpt,
            "prompt_hash": prompt_hash,
            "created_by": request.created_by,
            "source": request.source,
            "context_refs": sanitized_context_refs,
            "metadata": sanitized_metadata,
        }
        message_values = {
            "id": message_id,
            "task_id": task_id,
            "program_id": request.program_id,
            "campaign_id": request.campaign_id,
            "correlation_id": request.correlation_id,
            "role": AgentTaskMessageRole.USER.value,
            "message_kind": AgentTaskMessageKind.NOTE.value,
            "agent_key": request.target_agent,
            "body": prompt_excerpt,
            "body_hash": body_hash(prompt_excerpt),
            "artifact_refs": [],
            "fact_refs": [],
            "graph_refs": [],
            "action_refs": [],
            "proposal_refs": [],
            "decision_refs": [],
            "metadata": {},
        }
        inbox_statement = (
            insert(agent_inbox)
            .values(
                program_id=request.program_id,
                campaign_id=request.campaign_id,
                correlation_id=request.correlation_id,
                message_type=AGENT_TASK_PROMPT_MESSAGE_TYPE,
                payload=inbox_payload,
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(agent_inbox.c.id)
        )

        async with self.session_factory() as session:
            task_result = await session.execute(
                sa_insert(agent_tasks).values(**task_values).returning(agent_tasks)
            )
            message_result = await session.execute(
                sa_insert(agent_task_messages)
                .values(**message_values)
                .returning(agent_task_messages)
            )
            inbox_result = await session.execute(inbox_statement)
            inbox_message_id = inbox_result.scalar_one_or_none()
            if inbox_message_id is not None:
                await session.execute(
                    agent_tasks.update()
                    .where(agent_tasks.c.id == task_id)
                    .values(inbox_message_id=inbox_message_id)
                )
            if hasattr(session, "commit"):
                await session.commit()

            task_row = dict(task_result.mappings().one())
            if inbox_message_id is not None:
                task_row["inbox_message_id"] = inbox_message_id
            message_row = dict(message_result.mappings().one())

        return AgentTaskCreated(
            task=self._task_record(task_row),
            first_message=self._message_record(message_row),
            inbox_message_id=inbox_message_id,
        )

    async def list_tasks(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        status: AgentTaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskRecord]:
        query = select(agent_tasks).where(agent_tasks.c.program_id == program_id)
        if campaign_id is not None:
            query = query.where(agent_tasks.c.campaign_id == campaign_id)
        if status is not None:
            query = query.where(agent_tasks.c.status == status.value)
        query = query.order_by(agent_tasks.c.created_at.desc()).limit(max(1, limit)).offset(max(0, offset))
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self._task_record(dict(row)) for row in rows]

    async def list_task_messages(
        self,
        *,
        task_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTaskMessageRecord]:
        query = (
            select(agent_task_messages)
            .where(agent_task_messages.c.task_id == task_id)
            .order_by(agent_task_messages.c.created_at.asc())
            .limit(max(1, limit))
            .offset(max(0, offset))
        )
        async with self.session_factory() as session:
            result = await session.execute(query)
            rows = result.mappings().all()
        return [self._message_record(dict(row)) for row in rows]

    async def append_followup_message(
        self,
        *,
        task_id: UUID,
        message_id: UUID,
        request: AgentTaskFollowupRequest,
        body: str,
        body_hash: str,
        sanitized_context_refs: list[dict[str, Any]],
        sanitized_metadata: dict[str, Any],
        inbox_payload: dict[str, Any],
        dedupe_key: str,
    ) -> AgentTaskMessageRecord:
        async with self.session_factory() as session:
            task_result = await session.execute(
                select(
                    agent_tasks.c.id,
                    agent_tasks.c.program_id,
                    agent_tasks.c.campaign_id,
                    agent_tasks.c.correlation_id,
                    agent_tasks.c.target_agent,
                ).where(agent_tasks.c.id == task_id)
            )
            task_row = task_result.mappings().one()
            message_values = {
                "id": message_id,
                "task_id": task_id,
                "program_id": task_row["program_id"],
                "campaign_id": task_row["campaign_id"],
                "correlation_id": task_row["correlation_id"],
                "role": AgentTaskMessageRole.USER.value,
                "message_kind": AgentTaskMessageKind.NOTE.value,
                "agent_key": task_row["target_agent"],
                "body": body,
                "body_hash": body_hash,
                "artifact_refs": [],
                "fact_refs": [],
                "graph_refs": [],
                "action_refs": [],
                "proposal_refs": [],
                "decision_refs": [],
                "metadata": {
                    "source": request.source,
                    "created_by": request.created_by,
                    "context_refs": sanitized_context_refs,
                    **sanitized_metadata,
                },
            }
            message_result = await session.execute(
                sa_insert(agent_task_messages).values(**message_values).returning(agent_task_messages)
            )
            inbox_statement = (
                insert(agent_inbox)
                .values(
                    program_id=task_row["program_id"],
                    campaign_id=task_row["campaign_id"],
                    correlation_id=task_row["correlation_id"],
                    message_type=AGENT_TASK_PROMPT_MESSAGE_TYPE,
                    payload={
                        **inbox_payload,
                        "program_id": str(task_row["program_id"]),
                        "campaign_id": str(task_row["campaign_id"]) if task_row["campaign_id"] else None,
                        "correlation_id": str(task_row["correlation_id"]),
                        "target_agent": task_row["target_agent"],
                    },
                    dedupe_key=dedupe_key,
                )
                .on_conflict_do_nothing(index_elements=["dedupe_key"])
                .returning(agent_inbox.c.id)
            )
            await session.execute(inbox_statement)
            await session.execute(
                agent_tasks.update()
                .where(agent_tasks.c.id == task_id)
                .values(status=AgentTaskStatus.QUEUED.value)
            )
            message_row = dict(message_result.mappings().one())
            await _record_agent_runtime_usage_daily(session, message_row)
            if hasattr(session, "commit"):
                await session.commit()
        return self._message_record(message_row)

    async def append_agent_reply(
        self,
        *,
        task_id: UUID,
        message_id: UUID,
        request: AgentTaskAgentReplyRequest,
        body: str,
        body_hash: str,
        sanitized_refs: dict[str, list[dict[str, Any]]],
        sanitized_metadata: dict[str, Any],
    ) -> AgentTaskMessageRecord:
        async with self.session_factory() as session:
            task_result = await session.execute(
                select(
                    agent_tasks.c.id,
                    agent_tasks.c.program_id,
                    agent_tasks.c.campaign_id,
                    agent_tasks.c.correlation_id,
                ).where(agent_tasks.c.id == task_id)
            )
            task_row = task_result.mappings().one()
            message_values = {
                "id": message_id,
                "task_id": task_id,
                "program_id": task_row["program_id"],
                "campaign_id": task_row["campaign_id"],
                "correlation_id": task_row["correlation_id"],
                "role": AgentTaskMessageRole.AGENT.value,
                "message_kind": request.message_kind.value,
                "agent_key": request.agent_key,
                "body": body,
                "body_hash": body_hash,
                "artifact_refs": sanitized_refs["artifact_refs"],
                "fact_refs": sanitized_refs["fact_refs"],
                "graph_refs": sanitized_refs["graph_refs"],
                "action_refs": sanitized_refs["action_refs"],
                "proposal_refs": sanitized_refs["proposal_refs"],
                "decision_refs": sanitized_refs["decision_refs"],
                "metadata": sanitized_metadata,
            }
            message_result = await session.execute(
                sa_insert(agent_task_messages).values(**message_values).returning(agent_task_messages)
            )
            update_values = {}
            if request.status is not None:
                update_values["status"] = request.status.value
            if update_values:
                await session.execute(
                    agent_tasks.update()
                    .where(agent_tasks.c.id == task_id)
                    .values(**update_values)
                )
            message_row = dict(message_result.mappings().one())
            await _record_agent_runtime_usage_daily(session, message_row)
            if hasattr(session, "commit"):
                await session.commit()
        return self._message_record(message_row)

    @staticmethod
    def _task_record(row: dict[str, Any]) -> AgentTaskRecord:
        return AgentTaskRecord(
            task_id=row["id"],
            program_id=row["program_id"],
            campaign_id=row.get("campaign_id"),
            correlation_id=row["correlation_id"],
            status=AgentTaskStatus(row["status"]),
            target_agent=row["target_agent"],
            title=row["title"],
            prompt_excerpt=row["prompt_excerpt"],
            prompt_hash=row["prompt_hash"],
            created_by=row["created_by"],
            source=row["source"],
            context_refs=row.get("context_refs") or [],
            metadata=row.get("metadata") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            inbox_message_id=row.get("inbox_message_id"),
        )

    @staticmethod
    def _message_record(row: dict[str, Any]) -> AgentTaskMessageRecord:
        return AgentTaskMessageRecord(
            message_id=row["id"],
            task_id=row["task_id"],
            program_id=row["program_id"],
            campaign_id=row.get("campaign_id"),
            correlation_id=row["correlation_id"],
            role=AgentTaskMessageRole(row["role"]),
            message_kind=AgentTaskMessageKind(row.get("message_kind") or AgentTaskMessageKind.NOTE.value),
            agent_key=row.get("agent_key"),
            body=row["body"],
            body_hash=row["body_hash"],
            artifact_refs=row.get("artifact_refs") or [],
            fact_refs=row.get("fact_refs") or [],
            graph_refs=row.get("graph_refs") or [],
            action_refs=row.get("action_refs") or [],
            proposal_refs=row.get("proposal_refs") or [],
            decision_refs=row.get("decision_refs") or [],
            metadata=row.get("metadata") or {},
            created_at=row["created_at"],
        )


async def _record_agent_runtime_usage_daily(session, message_row: dict[str, Any]) -> None:
    """Persist one agent runtime budget decision into daily/campaign aggregate."""

    delta = runtime_usage_delta_from_metadata(message_row.get("metadata") or {})
    if delta is None:
        return

    created_at = _as_datetime(message_row.get("created_at"))
    usage_date = created_at.date()
    program_id = message_row["program_id"]
    campaign_id = message_row.get("campaign_id")
    scope_key = _runtime_usage_scope_key(
        program_id=program_id,
        campaign_id=campaign_id,
        usage_date=usage_date,
    )
    requested_column = f"requested_{delta.requested_mode}_count"
    selected_column = f"selected_{delta.selected_mode}_count"
    values = {
        "id": uuid4(),
        "scope_key": scope_key,
        "program_id": program_id,
        "campaign_id": campaign_id,
        "usage_date": usage_date,
        "total_agent_messages": 1,
        "runtime_decision_messages": 1,
        "requested_none_count": 0,
        "requested_cheap_count": 0,
        "requested_normal_count": 0,
        "requested_deep_count": 0,
        "selected_none_count": 0,
        "selected_cheap_count": 0,
        "selected_normal_count": 0,
        "selected_deep_count": 0,
        "llm_allowed_messages": 1 if delta.llm_allowed else 0,
        "no_model_messages": 0 if delta.llm_allowed else 1,
        "downgraded_messages": 1 if delta.downgraded else 0,
        "deep_requested_messages": 1 if delta.deep_requested else 0,
        "deep_approved_messages": 1 if delta.deep_approved else 0,
        "deep_downgraded_messages": 1 if delta.deep_downgraded else 0,
        "context_truncated_messages": 1 if delta.context_truncated else 0,
        "latest_message_id": message_row.get("id"),
        "latest_selected_mode": delta.selected_mode,
        "latest_requested_mode": delta.requested_mode,
        "latest_reason_code": delta.reason_code,
        "metadata": {"source": "agent_task_message_budget"},
    }
    values[requested_column] = 1
    values[selected_column] = 1

    statement = insert(agent_runtime_usage_daily).values(**values)
    increment_columns = (
        "total_agent_messages",
        "runtime_decision_messages",
        "requested_none_count",
        "requested_cheap_count",
        "requested_normal_count",
        "requested_deep_count",
        "selected_none_count",
        "selected_cheap_count",
        "selected_normal_count",
        "selected_deep_count",
        "llm_allowed_messages",
        "no_model_messages",
        "downgraded_messages",
        "deep_requested_messages",
        "deep_approved_messages",
        "deep_downgraded_messages",
        "context_truncated_messages",
    )
    set_values = {
        column: getattr(agent_runtime_usage_daily.c, column) + getattr(statement.excluded, column)
        for column in increment_columns
    }
    set_values.update(
        {
            "latest_message_id": statement.excluded.latest_message_id,
            "latest_selected_mode": statement.excluded.latest_selected_mode,
            "latest_requested_mode": statement.excluded.latest_requested_mode,
            "latest_reason_code": statement.excluded.latest_reason_code,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[agent_runtime_usage_daily.c.scope_key],
            set_=set_values,
        )
    )


def _runtime_usage_scope_key(*, program_id: UUID, campaign_id: UUID | None, usage_date) -> str:
    campaign_part = str(campaign_id) if campaign_id is not None else "none"
    return f"program:{program_id}:campaign:{campaign_part}:date:{usage_date.isoformat()}"


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.now(timezone.utc)
