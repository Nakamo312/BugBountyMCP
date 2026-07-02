"""Postgres read store for the campaign workroom UI."""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, or_, select

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
    event_dispatches,
    event_store,
    jobs,
    runs,
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
        active_run_statuses = ["queued", "leased", "running", "flushing", "failed"]
        terminal_success_statuses = ["completed", "cancelled", "dead"]
        terminal_jobs = jobs.alias("terminal_jobs")
        terminal_runs = runs.alias("terminal_runs")
        terminal_success_exists = (
            select(terminal_runs.c.id)
            .select_from(
                terminal_jobs.join(
                    terminal_runs, terminal_runs.c.job_id == terminal_jobs.c.id
                )
            )
            .where(terminal_jobs.c.action_id == action_requests.c.id)
            .where(terminal_runs.c.status.in_(terminal_success_statuses))
            .exists()
        )
        visible_request_statuses = [
            CampaignWorkspaceActionStatus.REQUIRES_APPROVAL.value,
            CampaignWorkspaceActionStatus.ALLOWED.value,
            CampaignWorkspaceActionStatus.BLOCKED.value,
        ]
        execution_join = (
            action_requests
            .outerjoin(jobs, jobs.c.action_id == action_requests.c.id)
            .outerjoin(runs, runs.c.job_id == jobs.c.id)
            .outerjoin(event_store, event_store.c.run_id == runs.c.id)
            .outerjoin(
                event_dispatches,
                and_(
                    event_dispatches.c.event_id == event_store.c.event_id,
                    event_dispatches.c.destination == "rabbitmq",
                ),
            )
        )
        statement = (
            select(
                action_requests,
                jobs.c.id.label("job_id"),
                jobs.c.status.label("job_status"),
                runs.c.id.label("run_id"),
                runs.c.status.label("run_status"),
                runs.c.attempt.label("run_attempt"),
                runs.c.error.label("run_error"),
                runs.c.started_at.label("run_started_at"),
                runs.c.finished_at.label("run_finished_at"),
                runs.c.updated_at.label("run_updated_at"),
                runs.c.lease_owner.label("lease_owner"),
                runs.c.lease_expires_at.label("lease_expires_at"),
                event_store.c.event_id.label("event_id"),
                event_store.c.event_type.label("event_type"),
                event_dispatches.c.status.label("dispatch_status"),
                event_dispatches.c.attempts.label("dispatch_attempts"),
                event_dispatches.c.routing_key.label("dispatch_routing_key"),
                event_dispatches.c.last_error.label("dispatch_last_error"),
                event_dispatches.c.locked_by.label("dispatch_locked_by"),
                event_dispatches.c.locked_until.label("dispatch_locked_until"),
                event_dispatches.c.dispatched_at.label("dispatched_at"),
            )
            .select_from(execution_join)
            .where(action_requests.c.program_id == program_id)
            .where(
                or_(
                    action_requests.c.status.in_(visible_request_statuses),
                    and_(
                        action_requests.c.status == CampaignWorkspaceActionStatus.QUEUED.value,
                        ~terminal_success_exists,
                        or_(runs.c.status.is_(None), runs.c.status.in_(active_run_statuses)),
                    ),
                )
            )
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
    request = row.get("request") or {}
    targets = [str(item) for item in request.get("targets") or [] if item]
    queue_stage, queue_reason = _action_queue_explanation(row)
    status = CampaignWorkspaceActionStatus(row["status"])
    return CampaignWorkspaceActionQueueItem(
        action_id=row["id"],
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        status=status,
        capability_id=row["capability_id"],
        profile_id=row["profile_id"],
        requested_by=row["requested_by"],
        kind=row["kind"],
        metadata=row.get("metadata") or {},
        targets=targets,
        target_count=len(targets),
        options=dict(request.get("options") or {}),
        job_id=row.get("job_id"),
        job_status=row.get("job_status"),
        run_id=row.get("run_id"),
        run_status=row.get("run_status"),
        run_attempt=row.get("run_attempt"),
        run_error=row.get("run_error"),
        run_started_at=row.get("run_started_at"),
        run_finished_at=row.get("run_finished_at"),
        run_updated_at=row.get("run_updated_at"),
        lease_owner=row.get("lease_owner"),
        lease_expires_at=row.get("lease_expires_at"),
        event_id=row.get("event_id"),
        event_type=row.get("event_type"),
        dispatch_status=row.get("dispatch_status"),
        dispatch_attempts=int(row.get("dispatch_attempts") or 0),
        dispatch_routing_key=row.get("dispatch_routing_key"),
        dispatch_last_error=row.get("dispatch_last_error"),
        dispatch_locked_by=row.get("dispatch_locked_by"),
        dispatch_locked_until=row.get("dispatch_locked_until"),
        dispatched_at=row.get("dispatched_at"),
        queue_stage=queue_stage,
        queue_reason=queue_reason,
        can_approve=status is CampaignWorkspaceActionStatus.REQUIRES_APPROVAL,
        can_reject=status is CampaignWorkspaceActionStatus.REQUIRES_APPROVAL,
        can_cancel=_can_cancel_action(row),
        cancel_reason=_cancel_reason(row),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _can_cancel_action(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    run_status = row.get("run_status")
    if status in {
        CampaignWorkspaceActionStatus.REQUIRES_APPROVAL.value,
        CampaignWorkspaceActionStatus.ALLOWED.value,
    }:
        return True
    if status != CampaignWorkspaceActionStatus.QUEUED.value:
        return False
    return run_status in {None, "queued", "failed", "dead"}


def _cancel_reason(row: dict[str, Any]) -> str | None:
    status = str(row.get("status") or "")
    run_status = row.get("run_status")
    if _can_cancel_action(row):
        return None
    if status == CampaignWorkspaceActionStatus.QUEUED.value and run_status in {"leased", "running", "flushing"}:
        return "Worker already started this action; queued cancellation cannot stop a live runner."
    return "This action is not in a cancellable queue state."


def _action_queue_explanation(row: dict[str, Any]) -> tuple[str, str]:
    status = str(row.get("status") or "")
    run_status = row.get("run_status")
    dispatch_status = row.get("dispatch_status")
    if status == CampaignWorkspaceActionStatus.REQUIRES_APPROVAL.value:
        return (
            "approval",
            "Waiting for human approval. No execution job is released until this action is approved.",
        )
    if status == CampaignWorkspaceActionStatus.BLOCKED.value:
        return ("policy", "Blocked by scope, policy, or budget before execution was queued.")
    if status == CampaignWorkspaceActionStatus.ALLOWED.value:
        return ("policy", "Allowed by policy, but no execution job has been released yet.")
    if not row.get("job_id"):
        return (
            "job_missing",
            "Action request is queued, but the execution job row is missing. This is an inconsistent control-plane state.",
        )
    if not row.get("event_id"):
        return (
            "event_missing",
            "Execution job exists, but no durable event was recorded for the pipeline dispatcher.",
        )
    if dispatch_status in {"pending", "locked", "failed", "dead"}:
        if dispatch_status == "pending":
            return ("dispatch", "Waiting for the event dispatcher to publish the stored event to RabbitMQ.")
        if dispatch_status == "locked":
            return ("dispatch", "Event dispatcher has leased this event and is publishing it to RabbitMQ.")
        if dispatch_status == "failed":
            return ("dispatch", "Event dispatch to RabbitMQ failed and is waiting for retry.")
        return ("dispatch", "Event dispatch to RabbitMQ is dead after retry exhaustion.")
    if dispatch_status == "dispatched" and run_status == "queued":
        return (
            "worker",
            "Event was published to RabbitMQ. Waiting for NodeRegistry/pipeline worker to consume the routing key and claim the run.",
        )
    if run_status == "leased":
        return ("worker", "Pipeline worker leased the run and should move it to running before the lease expires.")
    if run_status == "running":
        return ("running", "Tool runner is executing this action.")
    if run_status == "flushing":
        return ("flushing", "Tool output is being ingested into artifacts, surface, projections, and outcomes.")
    if run_status == "failed":
        return ("retry", "Run failed and may be retried or reconciled by the pipeline scheduler.")
    return ("queued", "Queued for execution, but no more specific runtime state is available.")
