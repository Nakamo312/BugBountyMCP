"""Postgres read store for a concrete agent task screen."""
from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select

from api.application.agent_action_proposals import AgentActionProposalStatus
from api.application.agent_task_detail import (
    AgentTaskDetailContext,
    AgentTaskDetailOutcomeItem,
    AgentTaskDetailSnapshot,
    now_utc,
    task_detail_boundaries,
    task_detail_counts,
)
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskMessageRole
from api.application.agent_runtime_usage import summarize_agent_runtime_usage
from api.application.campaign_workspace import (
    CampaignWorkspaceActionQueueItem,
    CampaignWorkspaceActionStatus,
)
from api.infrastructure.adapters.orm import (
    action_outcomes,
    action_requests,
    agent_action_proposals,
    agent_task_messages,
    agent_tasks,
    endpoints,
    hosts,
    http_observations,
    javascript_references,
)
from api.infrastructure.agent_action_proposals import AgentActionProposalStore
from api.infrastructure.agent_tasks import AgentTaskStore


class AgentTaskDetailStore:
    """Build a focused task detail payload from durable state.

    This store deliberately stays read-only and pointer-oriented. It does not
    read raw artifacts, raw response bodies, or trigger internal computation.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def load_task_detail(
        self,
        *,
        task_id: UUID,
        message_limit: int = 100,
        proposal_limit: int = 50,
        outcome_limit: int = 20,
        surface_sample_limit: int = 8,
    ) -> AgentTaskDetailSnapshot | None:
        async with self.session_factory() as session:
            task_row = await self._load_task(session, task_id=task_id)
            if task_row is None:
                return None
            message_rows = await self._load_messages(session, task_id=task_id, limit=message_limit)
            proposal_rows = await self._load_proposals(session, task_id=task_id, limit=proposal_limit)
            accepted_action_ids = [row["accepted_action_id"] for row in proposal_rows if row.get("accepted_action_id")]
            action_rows = await self._load_accepted_actions(session, action_ids=accepted_action_ids)
            outcome_rows = await self._load_related_outcomes(
                session,
                task_row=task_row,
                accepted_action_ids=accepted_action_ids,
                limit=outcome_limit,
            )
            surface_summary = await self._load_surface_summary(
                session,
                program_id=task_row["program_id"],
                sample_limit=surface_sample_limit,
            )

        task = AgentTaskStore._task_record(task_row)
        messages = [AgentTaskStore._message_record(row) for row in message_rows]
        proposals = [AgentActionProposalStore._record(row) for row in proposal_rows]
        accepted_actions = [_action_queue_item(row) for row in action_rows]
        related_outcomes = [_outcome_item(row) for row in outcome_rows]
        decisions = [message for message in messages if message.message_kind is AgentTaskMessageKind.DECISION]
        snapshot = AgentTaskDetailSnapshot(
            task=task,
            messages=messages,
            proposals=proposals,
            decisions=decisions,
            accepted_actions=accepted_actions,
            related_outcomes=related_outcomes,
            compact_context=_compact_context(
                task_row=task_row,
                messages=messages,
                proposals=proposals,
                accepted_actions=accepted_actions,
                related_outcomes=related_outcomes,
                surface_summary=surface_summary,
            ),
            generated_at=now_utc(),
        )
        return snapshot.model_copy(update={"counts": task_detail_counts(snapshot)})

    async def _load_task(self, session, *, task_id: UUID) -> dict[str, Any] | None:
        result = await session.execute(select(agent_tasks).where(agent_tasks.c.id == task_id))
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None

    async def _load_messages(self, session, *, task_id: UUID, limit: int) -> list[dict[str, Any]]:
        statement = (
            select(agent_task_messages)
            .where(agent_task_messages.c.task_id == task_id)
            .order_by(agent_task_messages.c.created_at.asc(), agent_task_messages.c.id.asc())
            .limit(max(1, limit))
        )
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_proposals(self, session, *, task_id: UUID, limit: int) -> list[dict[str, Any]]:
        statement = (
            select(agent_action_proposals)
            .where(agent_action_proposals.c.task_id == task_id)
            .order_by(desc(agent_action_proposals.c.created_at), desc(agent_action_proposals.c.id))
            .limit(max(1, limit))
        )
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_accepted_actions(self, session, *, action_ids: list[UUID]) -> list[dict[str, Any]]:
        if not action_ids:
            return []
        statement = (
            select(action_requests)
            .where(action_requests.c.id.in_(action_ids))
            .order_by(desc(action_requests.c.created_at))
        )
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_related_outcomes(
        self,
        session,
        *,
        task_row: dict[str, Any],
        accepted_action_ids: list[UUID],
        limit: int,
    ) -> list[dict[str, Any]]:
        # Prefer outcomes from actions accepted from this task. If no accepted
        # action exists yet, show recent campaign/program outcomes as compact
        # memory so the agent task screen still has useful context.
        statement = select(action_outcomes).where(action_outcomes.c.program_id == task_row["program_id"])
        if accepted_action_ids:
            statement = statement.where(action_outcomes.c.action_id.in_(accepted_action_ids))
        elif task_row.get("campaign_id") is not None:
            statement = statement.where(action_outcomes.c.campaign_id == task_row["campaign_id"])
        statement = statement.order_by(desc(action_outcomes.c.created_at), desc(action_outcomes.c.id)).limit(max(1, limit))
        result = await session.execute(statement)
        return [dict(row) for row in result.mappings().all()]

    async def _load_surface_summary(
        self,
        session,
        *,
        program_id: UUID,
        sample_limit: int,
    ) -> dict[str, Any]:
        host_count = await _scalar_count(session, select(func.count()).select_from(hosts).where(hosts.c.program_id == program_id))
        endpoint_count = await _scalar_count(
            session,
            select(func.count())
            .select_from(endpoints.join(hosts, endpoints.c.host_id == hosts.c.id))
            .where(hosts.c.program_id == program_id),
        )
        http_count = await _scalar_count(
            session,
            select(func.count()).select_from(http_observations).where(http_observations.c.program_id == program_id),
        )
        js_count = await _scalar_count(
            session,
            select(func.count()).select_from(javascript_references).where(javascript_references.c.program_id == program_id),
        )
        http_samples = await _recent_http_samples(session, program_id=program_id, limit=sample_limit)
        js_samples = await _recent_js_samples(session, program_id=program_id, limit=sample_limit)
        return {
            "counts": {
                "hosts": host_count,
                "endpoints": endpoint_count,
                "http_observations": http_count,
                "javascript_references": js_count,
            },
            "recent_http": http_samples,
            "recent_javascript": js_samples,
            "raw_artifact_access": "forbidden",
        }


async def _scalar_count(session, statement) -> int:
    result = await session.execute(statement)
    return int(result.scalar_one() or 0)


async def _recent_http_samples(session, *, program_id: UUID, limit: int) -> list[dict[str, Any]]:
    statement = (
        select(
            http_observations.c.id,
            http_observations.c.method,
            http_observations.c.url,
            http_observations.c.status_code,
            http_observations.c.content_type,
            http_observations.c.source_tool,
            http_observations.c.observed_at,
        )
        .where(http_observations.c.program_id == program_id)
        .order_by(desc(http_observations.c.observed_at), desc(http_observations.c.id))
        .limit(max(1, limit))
    )
    result = await session.execute(statement)
    return [
        {
            "kind": "http_observation",
            "observation_id": str(row["id"]),
            "method": row.get("method"),
            "url_excerpt": _safe_text(row.get("url"), limit=240),
            "status_code": row.get("status_code"),
            "content_type": _safe_text(row.get("content_type"), limit=120),
            "source_tool": row.get("source_tool"),
            "observed_at": _datetime_text(row.get("observed_at")),
        }
        for row in (dict(row) for row in result.mappings().all())
    ]


async def _recent_js_samples(session, *, program_id: UUID, limit: int) -> list[dict[str, Any]]:
    statement = (
        select(
            javascript_references.c.id,
            javascript_references.c.source_url,
            javascript_references.c.referenced_url,
            javascript_references.c.reference_type,
            javascript_references.c.source_tool,
            javascript_references.c.observed_at,
        )
        .where(javascript_references.c.program_id == program_id)
        .order_by(desc(javascript_references.c.observed_at), desc(javascript_references.c.id))
        .limit(max(1, limit))
    )
    result = await session.execute(statement)
    return [
        {
            "kind": "javascript_reference",
            "reference_id": str(row["id"]),
            "source_url_excerpt": _safe_text(row.get("source_url"), limit=220),
            "referenced_url_excerpt": _safe_text(row.get("referenced_url"), limit=220),
            "reference_type": row.get("reference_type"),
            "source_tool": row.get("source_tool"),
            "observed_at": _datetime_text(row.get("observed_at")),
        }
        for row in (dict(row) for row in result.mappings().all())
    ]


def _compact_context(
    *,
    task_row: dict[str, Any],
    messages,
    proposals,
    accepted_actions,
    related_outcomes,
    surface_summary: dict[str, Any],
) -> AgentTaskDetailContext:
    message_roles = Counter(message.role.value for message in messages)
    message_kinds = Counter(message.message_kind.value for message in messages)
    proposal_statuses = Counter(proposal.status.value for proposal in proposals)
    action_statuses = Counter(action.status.value for action in accepted_actions)
    last_user = next((message for message in reversed(messages) if message.role is AgentTaskMessageRole.USER), None)
    last_agent = next((message for message in reversed(messages) if message.role is AgentTaskMessageRole.AGENT), None)
    avg_gain = 0.0
    if related_outcomes:
        avg_gain = sum(outcome.information_gain_score for outcome in related_outcomes) / len(related_outcomes)
    return AgentTaskDetailContext(
        context_refs=task_row.get("context_refs") or [],
        thread_summary={
            "messages": len(messages),
            "user_messages": int(message_roles.get("user", 0)),
            "agent_messages": int(message_roles.get("agent", 0)),
            "proposal_messages": int(message_kinds.get("proposal", 0)),
            "finding_messages": int(message_kinds.get("finding", 0)),
            "decision_messages": int(message_kinds.get("decision", 0)),
        },
        proposal_summary={
            "total": len(proposals),
            "pending": int(proposal_statuses.get(AgentActionProposalStatus.PENDING.value, 0)),
            "accepted": int(proposal_statuses.get(AgentActionProposalStatus.ACCEPTED.value, 0)),
            "rejected": int(proposal_statuses.get(AgentActionProposalStatus.REJECTED.value, 0)),
            "suppressed": int(proposal_statuses.get(AgentActionProposalStatus.SUPPRESSED.value, 0)),
        },
        action_summary={
            "accepted_actions": len(accepted_actions),
            "queued": int(action_statuses.get(CampaignWorkspaceActionStatus.QUEUED.value, 0)),
            "requires_approval": int(action_statuses.get(CampaignWorkspaceActionStatus.REQUIRES_APPROVAL.value, 0)),
            "blocked": int(action_statuses.get(CampaignWorkspaceActionStatus.BLOCKED.value, 0)),
        },
        outcome_summary={
            "related_outcomes": len(related_outcomes),
            "avg_information_gain_score": round(avg_gain, 4),
            "high_gain_outcomes": sum(1 for outcome in related_outcomes if outcome.information_gain_score >= 0.7),
            "manual_interest_count": sum(1 for outcome in related_outcomes if outcome.human_feedback.get("manual_interest") is True),
            "manual_stop_count": sum(1 for outcome in related_outcomes if outcome.human_feedback.get("manual_stop") is True),
        },
        agent_runtime_usage=summarize_agent_runtime_usage(messages),
        surface_summary=surface_summary,
        last_user_message_excerpt=_safe_text(last_user.body, limit=700) if last_user else None,
        last_agent_message_excerpt=_safe_text(last_agent.body, limit=700) if last_agent else None,
        boundaries=task_detail_boundaries(),
    )


def _outcome_item(row: dict[str, Any]) -> AgentTaskDetailOutcomeItem:
    return AgentTaskDetailOutcomeItem(
        outcome_id=row["id"],
        program_id=row["program_id"],
        campaign_id=row.get("campaign_id"),
        action_id=row["action_id"],
        run_id=row["run_id"],
        capability_id=row["capability_id"],
        profile_id=row["profile_id"],
        node_id=row.get("node_id"),
        event_name=row.get("event_name"),
        status=row["status"],
        terminal_outcome=row.get("terminal_outcome"),
        information_gain_score=float(row.get("information_gain_score") or 0.0),
        counts={
            "hosts": int(row.get("observed_hosts_count") or 0),
            "services": int(row.get("observed_services_count") or 0),
            "endpoints": int(row.get("observed_endpoints_count") or 0),
            "http_observations": int(row.get("http_observation_count") or 0),
            "javascript_references": int(row.get("javascript_reference_count") or 0),
        },
        human_feedback={
            "manual_interest": row.get("manual_interest"),
            "manual_stop": row.get("manual_stop"),
            "continued_by_followup": row.get("continued_by_followup"),
            "report_created": row.get("report_created"),
            "triage_outcome": row.get("triage_outcome"),
        },
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


def _safe_text(value: Any, *, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _datetime_text(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
