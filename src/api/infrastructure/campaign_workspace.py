"""Postgres read store for the campaign workroom UI."""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select

from api.application.agent_action_proposals import AgentActionProposalStatus
from api.application.campaign_workspace import (
    CampaignWorkspaceActionQueueItem,
    CampaignWorkspaceActionStatus,
    CampaignWorkspaceExperienceProposalItem,
    CampaignWorkspaceSnapshot,
    CampaignWorkspaceTaskCard,
    now_utc,
    workspace_boundaries,
    workspace_counts,
)
from api.application.agent_tasks import AgentTaskMessageKind
from api.application.agent_runtime_usage import (
    summarize_agent_runtime_usage,
    summarize_agent_runtime_usage_aggregates,
)
from api.infrastructure.adapters.orm import (
    action_experience_proposals,
    action_requests,
    agent_action_proposals,
    agent_runtime_usage_daily,
    agent_task_messages,
    agent_tasks,
)
from api.infrastructure.agent_action_proposals import AgentActionProposalStore
from api.infrastructure.agent_tasks import AgentTaskStore


class CampaignWorkspaceStore:
    """Build a single UI payload from durable Postgres state.

    This store deliberately stays read-only. It does not trigger agents, GDS, or
    tool execution; it only assembles state already produced by internal workers
    and the ActionService boundary.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def load_workspace(
        self,
        *,
        program_id: UUID,
        campaign_id: UUID | None = None,
        task_limit: int = 20,
        message_limit_per_task: int = 8,
        proposal_limit: int = 20,
        action_limit: int = 20,
    ) -> CampaignWorkspaceSnapshot:
        async with self.session_factory() as session:
            task_rows = await self._load_tasks(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                limit=task_limit,
            )
            task_ids = [row["id"] for row in task_rows]
            message_rows = await self._load_messages(
                session,
                task_ids=task_ids,
                limit_per_task=message_limit_per_task,
            )
            agent_proposal_rows = await self._load_agent_proposals(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                task_ids=task_ids,
                limit=proposal_limit,
            )
            experience_proposal_rows = await self._load_experience_proposals(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                limit=proposal_limit,
            )
            action_rows = await self._load_action_queue(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                limit=action_limit,
            )
            runtime_usage_rows = await self._load_runtime_usage_daily(
                session,
                program_id=program_id,
                campaign_id=campaign_id,
                days=7,
            )

        messages_by_task = _group_messages_by_task(message_rows, limit_per_task=message_limit_per_task)
        proposals_by_task = _group_agent_proposals_by_task(agent_proposal_rows)
        tasks = [
            CampaignWorkspaceTaskCard(
                task=AgentTaskStore._task_record(row),
                messages=messages_by_task.get(row["id"], []),
                proposals=proposals_by_task.get(row["id"], []),
                decisions=[
                    message
                    for message in messages_by_task.get(row["id"], [])
                    if message.message_kind is AgentTaskMessageKind.DECISION
                ],
            )
            for row in task_rows
        ]
        recent_decisions = _recent_decisions(messages_by_task)
        pending_agent_proposals = [
            proposal
            for proposal in (AgentActionProposalStore._record(row) for row in agent_proposal_rows)
            if proposal.status is AgentActionProposalStatus.PENDING
        ]
        all_visible_messages = [message for messages in messages_by_task.values() for message in messages]
        runtime_usage = (
            summarize_agent_runtime_usage_aggregates(_runtime_usage_records(runtime_usage_rows))
            if runtime_usage_rows
            else summarize_agent_runtime_usage(all_visible_messages)
        )
        snapshot = CampaignWorkspaceSnapshot(
            program_id=program_id,
            campaign_id=campaign_id,
            generated_at=now_utc(),
            tasks=tasks,
            pending_agent_proposals=pending_agent_proposals,
            pending_experience_proposals=[
                _experience_proposal_item(row) for row in experience_proposal_rows
            ],
            recent_decisions=recent_decisions,
            action_queue=[_action_queue_item(row) for row in action_rows],
            agent_runtime_usage=runtime_usage,
            boundaries=workspace_boundaries(),
        )
        return snapshot.model_copy(update={"counts": workspace_counts(snapshot)})

    async def _load_tasks(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(agent_tasks).where(agent_tasks.c.program_id == program_id)
        if campaign_id is not None:
            statement = statement.where(agent_tasks.c.campaign_id == campaign_id)
        statement = statement.order_by(desc(agent_tasks.c.updated_at), desc(agent_tasks.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_messages(
        self,
        session,
        *,
        task_ids: list[UUID],
        limit_per_task: int,
    ) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        statement = (
            select(agent_task_messages)
            .where(agent_task_messages.c.task_id.in_(task_ids))
            .order_by(desc(agent_task_messages.c.created_at))
            .limit(max(1, len(task_ids) * limit_per_task))
        )
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_agent_proposals(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        task_ids: list[UUID],
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = select(agent_action_proposals).where(agent_action_proposals.c.program_id == program_id)
        if campaign_id is not None:
            statement = statement.where(agent_action_proposals.c.campaign_id == campaign_id)
        if task_ids:
            statement = statement.where(agent_action_proposals.c.task_id.in_(task_ids))
        statement = statement.order_by(desc(agent_action_proposals.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_experience_proposals(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = (
            select(action_experience_proposals)
            .where(action_experience_proposals.c.program_id == program_id)
            .where(action_experience_proposals.c.status.in_(["pending", "accepting", "accept_failed"]))
        )
        if campaign_id is not None:
            statement = statement.where(action_experience_proposals.c.campaign_id == campaign_id)
        statement = statement.order_by(action_experience_proposals.c.rank.asc(), desc(action_experience_proposals.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_action_queue(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        active_statuses = [
            CampaignWorkspaceActionStatus.QUEUED.value,
            CampaignWorkspaceActionStatus.REQUIRES_APPROVAL.value,
            CampaignWorkspaceActionStatus.ALLOWED.value,
            CampaignWorkspaceActionStatus.BLOCKED.value,
        ]
        statement = (
            select(action_requests)
            .where(action_requests.c.program_id == program_id)
            .where(action_requests.c.status.in_(active_statuses))
        )
        if campaign_id is not None:
            statement = statement.where(action_requests.c.campaign_id == campaign_id)
        statement = statement.order_by(desc(action_requests.c.created_at)).limit(limit)
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_runtime_usage_daily(
        self,
        session,
        *,
        program_id: UUID,
        campaign_id: UUID | None,
        days: int,
    ) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc).date() - timedelta(days=max(0, days - 1))
        statement = (
            select(agent_runtime_usage_daily)
            .where(agent_runtime_usage_daily.c.program_id == program_id)
            .where(agent_runtime_usage_daily.c.usage_date >= since)
        )
        if campaign_id is not None:
            statement = statement.where(agent_runtime_usage_daily.c.campaign_id == campaign_id)
        statement = statement.order_by(desc(agent_runtime_usage_daily.c.usage_date)).limit(max(1, days))
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]



def _runtime_usage_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "program_id": row["program_id"],
                "campaign_id": row.get("campaign_id"),
                "usage_date": row["usage_date"],
                "total_agent_messages": row.get("total_agent_messages") or 0,
                "runtime_decision_messages": row.get("runtime_decision_messages") or 0,
                "selected_modes": {
                    "none": row.get("selected_none_count") or 0,
                    "cheap": row.get("selected_cheap_count") or 0,
                    "normal": row.get("selected_normal_count") or 0,
                    "deep": row.get("selected_deep_count") or 0,
                },
                "requested_modes": {
                    "none": row.get("requested_none_count") or 0,
                    "cheap": row.get("requested_cheap_count") or 0,
                    "normal": row.get("requested_normal_count") or 0,
                    "deep": row.get("requested_deep_count") or 0,
                },
                "llm_allowed_messages": row.get("llm_allowed_messages") or 0,
                "no_model_messages": row.get("no_model_messages") or 0,
                "downgraded_messages": row.get("downgraded_messages") or 0,
                "deep_requested_messages": row.get("deep_requested_messages") or 0,
                "deep_approved_messages": row.get("deep_approved_messages") or 0,
                "deep_downgraded_messages": row.get("deep_downgraded_messages") or 0,
                "context_truncated_messages": row.get("context_truncated_messages") or 0,
                "latest_selected_mode": row.get("latest_selected_mode"),
                "latest_requested_mode": row.get("latest_requested_mode"),
                "latest_reason_code": row.get("latest_reason_code"),
            }
        )
    return records

def _group_messages_by_task(
    rows: list[dict[str, Any]],
    *,
    limit_per_task: int,
):
    grouped: dict[UUID, list] = defaultdict(list)
    for row in rows:
        grouped[row["task_id"]].append(AgentTaskStore._message_record(row))
    for task_id, messages in grouped.items():
        grouped[task_id] = sorted(messages, key=lambda item: item.created_at)[-limit_per_task:]
    return dict(grouped)


def _group_agent_proposals_by_task(rows: list[dict[str, Any]]):
    grouped: dict[UUID, list] = defaultdict(list)
    for row in rows:
        grouped[row["task_id"]].append(AgentActionProposalStore._record(row))
    return dict(grouped)


def _recent_decisions(messages_by_task: dict[UUID, list]):
    decisions = [
        message
        for messages in messages_by_task.values()
        for message in messages
        if message.message_kind is AgentTaskMessageKind.DECISION
    ]
    return sorted(decisions, key=lambda item: item.created_at, reverse=True)[:20]


def _experience_proposal_item(row: dict[str, Any]) -> CampaignWorkspaceExperienceProposalItem:
    return CampaignWorkspaceExperienceProposalItem(
        proposal_id=row["id"],
        proposal_run_id=row["proposal_run_id"],
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        status=row["status"],
        rank=row["rank"],
        capability_id=row["capability_id"],
        profile_id=row["profile_id"],
        utility_score=float(row.get("utility_score") or 0.0),
        sample_count=int(row.get("sample_count") or 0),
        avg_similarity=float(row.get("avg_similarity") or 0.0),
        explanation=row.get("explanation") or {},
        created_at=row["created_at"],
    )


def _action_queue_item(row: dict[str, Any]) -> CampaignWorkspaceActionQueueItem:
    return CampaignWorkspaceActionQueueItem(
        action_id=row["id"],
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        status=CampaignWorkspaceActionStatus(row["status"]),
        capability_id=row["capability_id"],
        profile_id=row["profile_id"],
        requested_by=row["requested_by"],
        kind=row["kind"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
