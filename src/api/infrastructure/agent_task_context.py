"""Bounded Postgres context reader for visible agent task runtimes.

The reader gives role agents compact, pointer-only context from canonical state.
It deliberately avoids raw artifacts, raw response bodies, shell output, and any
execution authority. LangGraph/LLM nodes can use this summary to answer in the
live task thread without becoming a new data ingestion or tool execution path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, func, select

from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest
from api.application.langgraph.task.agent.models import AgentTaskContextReader
from api.infrastructure.adapters.orm import (
    action_experience_proposals,
    action_outcomes,
    agent_task_messages,
    agent_tasks,
    endpoints,
    hosts,
    http_observations,
    javascript_references,
)


@dataclass(frozen=True, slots=True)
class PostgresAgentTaskContextReader:
    """Read compact context for an agent task from canonical Postgres tables.

    This is not a raw data reader. It returns bounded summaries and refs only:
    task metadata, recent thread messages, action outcome memory, pending
    experience proposals, and surface counters/samples. Raw artifacts stay out
    of agent context and remain available only through explicit evidence/artifact
    boundaries.
    """

    session_factory: Any
    max_request_context_refs: int = 25
    max_thread_messages: int = 8
    max_recent_outcomes: int = 8
    max_pending_proposals: int = 5
    max_surface_samples: int = 8

    async def read(self, request: AgentTaskRuntimeRequest) -> dict[str, Any]:
        context: dict[str, Any] = self._base_context(request)
        async with self.session_factory() as session:
            task = await self._read_task(session, request)
            if task:
                context["task"] = task
                context["context_refs"] = _dedupe_refs(
                    [*context["context_refs"], *task.get("context_refs", [])],
                    limit=self.max_request_context_refs,
                )
            context["thread_messages"] = await self._read_thread_messages(session, request)
            context["recent_outcomes"] = await self._read_recent_outcomes(session, request)
            context["pending_proposals"] = await self._read_pending_proposals(session, request)
            context["surface_summary"] = await self._read_surface_summary(session, request)
        context["context_reader"] = {
            "name": "postgres-agent-task-context.v1",
            "raw_artifact_access": "forbidden",
            "max_request_context_refs": self.max_request_context_refs,
            "max_thread_messages": self.max_thread_messages,
            "max_recent_outcomes": self.max_recent_outcomes,
            "max_pending_proposals": self.max_pending_proposals,
            "max_surface_samples": self.max_surface_samples,
        }
        return context

    def _base_context(self, request: AgentTaskRuntimeRequest) -> dict[str, Any]:
        return {
            "program_id": str(request.program_id),
            "campaign_id": str(request.campaign_id) if request.campaign_id else None,
            "correlation_id": str(request.correlation_id) if request.correlation_id else None,
            "task_id": str(request.task_id),
            "message_id": str(request.message_id),
            "target_agent": request.target_agent,
            "context_refs": _bounded_dicts(request.context_refs, limit=self.max_request_context_refs),
            "metadata_keys": sorted(str(key) for key in request.metadata.keys())[:25],
        }

    async def _read_task(self, session: Any, request: AgentTaskRuntimeRequest) -> dict[str, Any] | None:
        result = await session.execute(
            select(
                agent_tasks.c.id,
                agent_tasks.c.program_id,
                agent_tasks.c.campaign_id,
                agent_tasks.c.correlation_id,
                agent_tasks.c.status,
                agent_tasks.c.target_agent,
                agent_tasks.c.title,
                agent_tasks.c.created_by,
                agent_tasks.c.source,
                agent_tasks.c.context_refs,
                agent_tasks.c.created_at,
            ).where(agent_tasks.c.id == request.task_id)
        )
        row = result.mappings().first()
        if not row:
            return None
        return {
            "task_id": str(row["id"]),
            "program_id": str(row["program_id"]),
            "campaign_id": _uuid_text(row.get("campaign_id")),
            "correlation_id": _uuid_text(row.get("correlation_id")),
            "status": row["status"],
            "target_agent": row["target_agent"],
            "title": row["title"],
            "created_by": row["created_by"],
            "source": row["source"],
            "context_refs": _bounded_dicts(row.get("context_refs") or [], limit=self.max_request_context_refs),
            "created_at": _datetime_text(row.get("created_at")),
        }

    async def _read_thread_messages(self, session: Any, request: AgentTaskRuntimeRequest) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                agent_task_messages.c.id,
                agent_task_messages.c.role,
                agent_task_messages.c.message_kind,
                agent_task_messages.c.agent_key,
                agent_task_messages.c.body,
                agent_task_messages.c.artifact_refs,
                agent_task_messages.c.fact_refs,
                agent_task_messages.c.graph_refs,
                agent_task_messages.c.action_refs,
                agent_task_messages.c.proposal_refs,
                agent_task_messages.c.decision_refs,
                agent_task_messages.c.created_at,
            )
            .where(agent_task_messages.c.task_id == request.task_id)
            .order_by(desc(agent_task_messages.c.created_at), desc(agent_task_messages.c.id))
            .limit(max(1, self.max_thread_messages))
        )
        rows = [dict(row) for row in result.mappings().all()]
        rows.reverse()
        return [
            {
                "message_id": str(row["id"]),
                "role": row["role"],
                "message_kind": row.get("message_kind") or "note",
                "agent_key": row.get("agent_key"),
                "body_excerpt": _safe_text(row.get("body"), limit=700),
                "artifact_ref_count": len(row.get("artifact_refs") or []),
                "fact_ref_count": len(row.get("fact_refs") or []),
                "graph_ref_count": len(row.get("graph_refs") or []),
                "action_ref_count": len(row.get("action_refs") or []),
                "proposal_ref_count": len(row.get("proposal_refs") or []),
                "decision_ref_count": len(row.get("decision_refs") or []),
                "created_at": _datetime_text(row.get("created_at")),
            }
            for row in rows
        ]

    async def _read_recent_outcomes(self, session: Any, request: AgentTaskRuntimeRequest) -> list[dict[str, Any]]:
        query = (
            select(
                action_outcomes.c.id,
                action_outcomes.c.action_id,
                action_outcomes.c.run_id,
                action_outcomes.c.capability_id,
                action_outcomes.c.profile_id,
                action_outcomes.c.node_id,
                action_outcomes.c.event_name,
                action_outcomes.c.status,
                action_outcomes.c.terminal_outcome,
                action_outcomes.c.raw_artifact_count,
                action_outcomes.c.observed_hosts_count,
                action_outcomes.c.observed_services_count,
                action_outcomes.c.observed_endpoints_count,
                action_outcomes.c.http_observation_count,
                action_outcomes.c.javascript_reference_count,
                action_outcomes.c.manual_interest,
                action_outcomes.c.manual_stop,
                action_outcomes.c.continued_by_followup,
                action_outcomes.c.report_created,
                action_outcomes.c.triage_outcome,
                action_outcomes.c.information_gain_score,
                action_outcomes.c.created_at,
            )
            .where(action_outcomes.c.program_id == request.program_id)
            .order_by(desc(action_outcomes.c.created_at), desc(action_outcomes.c.id))
            .limit(max(1, self.max_recent_outcomes))
        )
        if request.campaign_id is not None:
            query = query.where(action_outcomes.c.campaign_id == request.campaign_id)
        result = await session.execute(query)
        return [
            {
                "kind": "action_outcome",
                "outcome_id": str(row["id"]),
                "action_id": str(row["action_id"]),
                "run_id": str(row["run_id"]),
                "capability_id": row["capability_id"],
                "profile_id": row["profile_id"],
                "node_id": row.get("node_id"),
                "event_name": row.get("event_name"),
                "status": row["status"],
                "terminal_outcome": row.get("terminal_outcome"),
                "information_gain_score": float(row.get("information_gain_score") or 0.0),
                "counts": {
                    "raw_artifacts": int(row.get("raw_artifact_count") or 0),
                    "hosts": int(row.get("observed_hosts_count") or 0),
                    "services": int(row.get("observed_services_count") or 0),
                    "endpoints": int(row.get("observed_endpoints_count") or 0),
                    "http_observations": int(row.get("http_observation_count") or 0),
                    "javascript_references": int(row.get("javascript_reference_count") or 0),
                },
                "human_feedback": {
                    "manual_interest": row.get("manual_interest"),
                    "manual_stop": row.get("manual_stop"),
                    "continued_by_followup": row.get("continued_by_followup"),
                    "report_created": row.get("report_created"),
                    "triage_outcome": row.get("triage_outcome"),
                },
                "created_at": _datetime_text(row.get("created_at")),
            }
            for row in result.mappings().all()
        ]

    async def _read_pending_proposals(self, session: Any, request: AgentTaskRuntimeRequest) -> list[dict[str, Any]]:
        query = (
            select(
                action_experience_proposals.c.id,
                action_experience_proposals.c.proposal_run_id,
                action_experience_proposals.c.source_outcome_id,
                action_experience_proposals.c.capability_id,
                action_experience_proposals.c.profile_id,
                action_experience_proposals.c.status,
                action_experience_proposals.c.rank,
                action_experience_proposals.c.utility_score,
                action_experience_proposals.c.sample_count,
                action_experience_proposals.c.avg_similarity,
                action_experience_proposals.c.avg_information_gain_score,
                action_experience_proposals.c.human_positive_rate,
                action_experience_proposals.c.human_stop_rate,
                action_experience_proposals.c.explanation,
                action_experience_proposals.c.created_at,
            )
            .where(action_experience_proposals.c.program_id == request.program_id)
            .where(action_experience_proposals.c.status.in_(["pending", "accepting", "accept_failed"]))
            .order_by(action_experience_proposals.c.rank.asc(), desc(action_experience_proposals.c.utility_score))
            .limit(max(1, self.max_pending_proposals))
        )
        if request.campaign_id is not None:
            query = query.where(action_experience_proposals.c.campaign_id == request.campaign_id)
        result = await session.execute(query)
        return [
            {
                "kind": "action_experience_proposal",
                "proposal_id": str(row["id"]),
                "proposal_run_id": str(row["proposal_run_id"]),
                "source_outcome_id": str(row["source_outcome_id"]),
                "capability_id": row["capability_id"],
                "profile_id": row["profile_id"],
                "status": row.get("status") or "pending",
                "rank": int(row["rank"]),
                "utility_score": float(row.get("utility_score") or 0.0),
                "sample_count": int(row.get("sample_count") or 0),
                "avg_similarity": float(row.get("avg_similarity") or 0.0),
                "avg_information_gain_score": float(row.get("avg_information_gain_score") or 0.0),
                "human_positive_rate": float(row.get("human_positive_rate") or 0.0),
                "human_stop_rate": float(row.get("human_stop_rate") or 0.0),
                "explanation": _safe_json(row.get("explanation") or {}, limit=12),
                "created_at": _datetime_text(row.get("created_at")),
            }
            for row in result.mappings().all()
        ]

    async def _read_surface_summary(self, session: Any, request: AgentTaskRuntimeRequest) -> dict[str, Any]:
        host_count = await self._scalar_count(
            session,
            select(func.count()).select_from(hosts).where(hosts.c.program_id == request.program_id),
        )
        endpoint_count = await self._scalar_count(
            session,
            select(func.count())
            .select_from(endpoints.join(hosts, endpoints.c.host_id == hosts.c.id))
            .where(hosts.c.program_id == request.program_id),
        )
        http_count = await self._scalar_count(
            session,
            select(func.count()).select_from(http_observations).where(http_observations.c.program_id == request.program_id),
        )
        js_count = await self._scalar_count(
            session,
            select(func.count()).select_from(javascript_references).where(javascript_references.c.program_id == request.program_id),
        )
        recent_http = await self._recent_http_samples(session, request)
        recent_js = await self._recent_javascript_samples(session, request)
        return {
            "kind": "surface_summary",
            "program_id": str(request.program_id),
            "campaign_id": str(request.campaign_id) if request.campaign_id else None,
            "counts": {
                "hosts": host_count,
                "endpoints": endpoint_count,
                "http_observations": http_count,
                "javascript_references": js_count,
            },
            "recent_http": recent_http,
            "recent_javascript": recent_js,
            "raw_artifact_access": "forbidden",
        }

    async def _recent_http_samples(self, session: Any, request: AgentTaskRuntimeRequest) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                http_observations.c.id,
                http_observations.c.method,
                http_observations.c.url,
                http_observations.c.status_code,
                http_observations.c.content_type,
                http_observations.c.source_tool,
                http_observations.c.observed_at,
            )
            .where(http_observations.c.program_id == request.program_id)
            .order_by(desc(http_observations.c.observed_at), desc(http_observations.c.id))
            .limit(max(1, self.max_surface_samples))
        )
        return [
            {
                "kind": "http_observation",
                "observation_id": str(row["id"]),
                "method": row["method"],
                "url_excerpt": _safe_url(row.get("url")),
                "status_code": row.get("status_code"),
                "content_type": _safe_text(row.get("content_type"), limit=120),
                "source_tool": row["source_tool"],
                "observed_at": _datetime_text(row.get("observed_at")),
            }
            for row in result.mappings().all()
        ]

    async def _recent_javascript_samples(self, session: Any, request: AgentTaskRuntimeRequest) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                javascript_references.c.id,
                javascript_references.c.source_url,
                javascript_references.c.referenced_url,
                javascript_references.c.reference_type,
                javascript_references.c.source_tool,
                javascript_references.c.observed_at,
            )
            .where(javascript_references.c.program_id == request.program_id)
            .order_by(desc(javascript_references.c.observed_at), desc(javascript_references.c.id))
            .limit(max(1, self.max_surface_samples))
        )
        return [
            {
                "kind": "javascript_reference",
                "reference_id": str(row["id"]),
                "source_url_excerpt": _safe_url(row.get("source_url")),
                "referenced_url_excerpt": _safe_url(row.get("referenced_url")),
                "reference_type": row["reference_type"],
                "source_tool": row["source_tool"],
                "observed_at": _datetime_text(row.get("observed_at")),
            }
            for row in result.mappings().all()
        ]

    @staticmethod
    async def _scalar_count(session: Any, query: Any) -> int:
        result = await session.execute(query)
        value = result.scalar_one()
        return int(value or 0)


def _bounded_dicts(items: Any, *, limit: int) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    if not items:
        return bounded
    for item in list(items)[: max(0, limit)]:
        if isinstance(item, dict):
            bounded.append(_safe_json(item, limit=30))
    return bounded


def _dedupe_refs(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = f"{item.get('kind')}:{item.get('id') or item.get('ref') or item.get('url') or item}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _safe_json(value: Any, *, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": _safe_text(value, limit=1000)}
    safe: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= limit:
            break
        safe[str(key)[:120]] = _safe_value(item)
    return safe


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value, limit=1000)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return _safe_json(value, limit=10)
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:10]]
    return _safe_text(value, limit=1000)


def _safe_text(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[: max(0, limit)]


def _safe_url(value: Any) -> str:
    text = _safe_text(value, limit=500)
    if not text:
        return ""
    # Keep enough structure for human review, but never include response bodies.
    return text[:500]


def _uuid_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _datetime_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
