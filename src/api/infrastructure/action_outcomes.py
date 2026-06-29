"""Persistence for action outcome memory."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, distinct, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import (
    ActionOutcomeFeedback,
    ActionOutcomeFeedbackRecord,
    ActionOutcomeMeasures,
    ActionOutcomeRecord,
    ActionOutcomeScore,
    ExecutionStatus,
    TerminalOutcome,
)
from api.infrastructure.adapters.orm import (
    action_outcome_feedback_events,
    action_outcomes,
    endpoints,
    http_observations,
    javascript_references,
    jobs,
    raw_artifacts,
    runs,
)


@dataclass(frozen=True)
class ActionOutcomeDraft:
    """Measured run outcome ready for an external scoring policy."""

    row: Mapping[str, Any]
    outcome_id: uuid.UUID
    measures: ActionOutcomeMeasures
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None


class ActionOutcomeStore:
    """Run-scoped persistence for measured action outcomes."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def load_run_outcome_draft(self, *, run_id: uuid.UUID) -> ActionOutcomeDraft | None:
        async with self.session_factory() as session:
            context_result = await session.execute(self._run_context_query(run_id))
            row = context_result.mappings().one_or_none()
            if row is None:
                return None

            measures = await self._collect_measures(session, run_id=run_id, row=row)
            return ActionOutcomeDraft(
                row=dict(row),
                outcome_id=row.get("outcome_id") or uuid.uuid4(),
                measures=measures,
                status=ExecutionStatus(row["status"]),
                terminal_outcome=self._optional_terminal_outcome(row.get("terminal_outcome")),
            )

    async def upsert_run_outcome(
        self,
        *,
        draft: ActionOutcomeDraft,
        score: ActionOutcomeScore,
    ) -> ActionOutcomeRecord:
        now = datetime.now(timezone.utc)
        values = self._values_from_row(
            row=draft.row,
            outcome_id=draft.outcome_id,
            measures=draft.measures,
            score=score,
            now=now,
        )
        stmt = pg_insert(action_outcomes).values(values)
        update_values = {
            key: value
            for key, value in values.items()
            if key not in {"id", "run_id", "created_at"}
        }
        update_values["updated_at"] = now

        async with self.session_factory() as session:
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[action_outcomes.c.run_id],
                    set_=update_values,
                )
            )
            await session.commit()

        return self._record_from_values(
            values={**values, "updated_at": now},
            measures=draft.measures,
            score=score,
        )

    async def apply_feedback(
        self,
        *,
        action_id: uuid.UUID,
        feedback: ActionOutcomeFeedback,
    ) -> ActionOutcomeFeedbackRecord | None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            target_result = await session.execute(
                self._feedback_target_query(action_id=action_id, run_id=feedback.run_id)
            )
            row = target_result.mappings().one_or_none()
            if row is None:
                return None

            event_id = uuid.uuid4()
            event_values = self._feedback_event_values(
                row=row,
                feedback_id=event_id,
                feedback=feedback,
                now=now,
            )
            await session.execute(insert(action_outcome_feedback_events).values(event_values))
            updates = self._feedback_update_values(feedback=feedback, now=now)
            if updates:
                await session.execute(
                    update(action_outcomes)
                    .where(action_outcomes.c.id == row["outcome_id"])
                    .values(**updates)
                )
            refreshed_result = await session.execute(
                select(action_outcomes).where(action_outcomes.c.id == row["outcome_id"])
            )
            refreshed = refreshed_result.mappings().one()
            await session.commit()

        outcome = self._record_from_outcome_row(refreshed)
        return ActionOutcomeFeedbackRecord(
            feedback_id=event_id,
            outcome_id=row["outcome_id"],
            program_id=row["program_id"],
            campaign_id=row.get("campaign_id"),
            action_id=row["action_id"],
            job_id=row["job_id"],
            run_id=row["run_id"],
            manual_interest=feedback.manual_interest,
            manual_stop=feedback.manual_stop,
            continued_by_followup=feedback.continued_by_followup,
            report_created=feedback.report_created,
            triage_outcome=feedback.triage_outcome,
            actor=feedback.actor,
            source=feedback.source,
            reason=feedback.reason,
            confidence=feedback.confidence,
            created_at=now,
            outcome=outcome,
        )

    @staticmethod
    def _feedback_target_query(*, action_id: uuid.UUID, run_id: uuid.UUID | None):
        query = (
            select(
                action_outcomes.c.id.label("outcome_id"),
                action_outcomes.c.program_id,
                action_outcomes.c.campaign_id,
                action_outcomes.c.action_id,
                action_outcomes.c.job_id,
                action_outcomes.c.run_id,
            )
            .where(action_outcomes.c.action_id == action_id)
            .order_by(
                desc(action_outcomes.c.finished_at),
                desc(action_outcomes.c.created_at),
                desc(action_outcomes.c.id),
            )
            .limit(1)
        )
        if run_id is not None:
            query = query.where(action_outcomes.c.run_id == run_id)
        return query

    @staticmethod
    def _feedback_update_values(
        *,
        feedback: ActionOutcomeFeedback,
        now: datetime,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {"updated_at": now}
        for field in (
            "manual_interest",
            "manual_stop",
            "continued_by_followup",
            "report_created",
            "triage_outcome",
        ):
            value = getattr(feedback, field)
            if value is not None:
                values[field] = value
        return values

    @staticmethod
    def _feedback_event_values(
        *,
        row: Mapping[str, Any],
        feedback_id: uuid.UUID,
        feedback: ActionOutcomeFeedback,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "id": feedback_id,
            "outcome_id": row["outcome_id"],
            "program_id": row["program_id"],
            "campaign_id": row.get("campaign_id"),
            "action_id": row["action_id"],
            "job_id": row["job_id"],
            "run_id": row["run_id"],
            "manual_interest": feedback.manual_interest,
            "manual_stop": feedback.manual_stop,
            "continued_by_followup": feedback.continued_by_followup,
            "report_created": feedback.report_created,
            "triage_outcome": feedback.triage_outcome,
            "actor": feedback.actor,
            "source": feedback.source,
            "reason": feedback.reason,
            "confidence": feedback.confidence,
            "created_at": now,
        }

    @staticmethod
    def _run_context_query(run_id: uuid.UUID):
        return (
            select(
                action_outcomes.c.id.label("outcome_id"),
                runs.c.id.label("run_id"),
                runs.c.job_id,
                runs.c.program_id,
                runs.c.node_id,
                runs.c.event_name,
                runs.c.status,
                runs.c.terminal_outcome,
                runs.c.attempt,
                runs.c.target_count,
                runs.c.run_payload,
                runs.c.started_at,
                runs.c.finished_at,
                runs.c.error,
                jobs.c.action_id,
                jobs.c.campaign_id,
                jobs.c.capability_id,
                jobs.c.profile_id,
                jobs.c.correlation_id,
            )
            .select_from(
                runs.join(jobs, runs.c.job_id == jobs.c.id).outerjoin(
                    action_outcomes,
                    action_outcomes.c.run_id == runs.c.id,
                )
            )
            .where(runs.c.id == run_id)
        )

    async def _collect_measures(
        self,
        session,
        *,
        run_id: uuid.UUID,
        row: Mapping[str, Any],
    ) -> ActionOutcomeMeasures:
        raw_stats = (
            await session.execute(
                select(
                    func.count(raw_artifacts.c.id).label("count"),
                    func.coalesce(func.sum(raw_artifacts.c.size_bytes), 0).label("bytes"),
                ).where(raw_artifacts.c.run_id == run_id)
            )
        ).mappings().one()
        http_stats = (
            await session.execute(
                select(
                    func.count(http_observations.c.id).label("count"),
                    func.count(distinct(http_observations.c.endpoint_id)).label("endpoints"),
                    func.count(distinct(http_observations.c.service_id)).label("services"),
                ).where(http_observations.c.run_id == run_id)
            )
        ).mappings().one()
        js_stats = (
            await session.execute(
                select(
                    func.count(javascript_references.c.id).label("count"),
                    func.count(distinct(javascript_references.c.endpoint_id)).label("endpoints"),
                    func.count(distinct(javascript_references.c.service_id)).label("services"),
                ).where(javascript_references.c.run_id == run_id)
            )
        ).mappings().one()
        host_count = await self._observed_host_count(session, run_id=run_id)
        return ActionOutcomeMeasures(
            raw_artifact_count=int(raw_stats["count"] or 0),
            raw_artifact_bytes=int(raw_stats["bytes"] or 0),
            observed_hosts_count=host_count,
            observed_services_count=max(
                int(http_stats["services"] or 0),
                int(js_stats["services"] or 0),
            ),
            observed_endpoints_count=max(
                int(http_stats["endpoints"] or 0),
                int(js_stats["endpoints"] or 0),
            ),
            http_observation_count=int(http_stats["count"] or 0),
            javascript_reference_count=int(js_stats["count"] or 0),
            duration_ms=self._duration_ms(row.get("started_at"), row.get("finished_at")),
            error_count=1 if row.get("error") else 0,
        )

    @staticmethod
    async def _observed_host_count(session, *, run_id: uuid.UUID) -> int:
        http_hosts = (
            select(endpoints.c.host_id.label("host_id"))
            .select_from(http_observations.join(endpoints, http_observations.c.endpoint_id == endpoints.c.id))
            .where(http_observations.c.run_id == run_id)
        )
        js_hosts = (
            select(endpoints.c.host_id.label("host_id"))
            .select_from(javascript_references.join(endpoints, javascript_references.c.endpoint_id == endpoints.c.id))
            .where(javascript_references.c.run_id == run_id)
        )
        host_ids = http_hosts.union_all(js_hosts).subquery()
        result = await session.execute(select(func.count(distinct(host_ids.c.host_id))))
        return int(result.scalar_one() or 0)

    @staticmethod
    def _duration_ms(started_at: datetime | None, finished_at: datetime | None) -> int | None:
        if started_at is None or finished_at is None:
            return None
        return max(0, int((finished_at - started_at).total_seconds() * 1000))

    @staticmethod
    def _target_count(row: Mapping[str, Any]) -> int | None:
        if row.get("target_count") is not None:
            return int(row["target_count"])
        payload = row.get("run_payload") or {}
        if isinstance(payload, Mapping):
            targets = payload.get("targets")
            if isinstance(targets, list):
                return len(targets)
            target = payload.get("target")
            if target:
                return 1
        return None

    @staticmethod
    def _optional_terminal_outcome(value: Any) -> TerminalOutcome | None:
        return TerminalOutcome(value) if value is not None else None

    @classmethod
    def _values_from_row(
        cls,
        *,
        row: Mapping[str, Any],
        outcome_id: uuid.UUID,
        measures: ActionOutcomeMeasures,
        score: ActionOutcomeScore,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "id": outcome_id,
            "program_id": row["program_id"],
            "campaign_id": row.get("campaign_id"),
            "action_id": row["action_id"],
            "job_id": row["job_id"],
            "run_id": row["run_id"],
            "capability_id": row["capability_id"],
            "profile_id": row["profile_id"],
            "node_id": row.get("node_id"),
            "event_name": row.get("event_name"),
            "correlation_id": row.get("correlation_id"),
            "status": row["status"],
            "terminal_outcome": row.get("terminal_outcome"),
            "attempt": int(row["attempt"]),
            "target_count": cls._target_count(row),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "duration_ms": measures.duration_ms,
            "error_count": measures.error_count,
            "error_message": row.get("error"),
            "raw_artifact_count": measures.raw_artifact_count,
            "raw_artifact_bytes": measures.raw_artifact_bytes,
            "observed_hosts_count": measures.observed_hosts_count,
            "observed_services_count": measures.observed_services_count,
            "observed_endpoints_count": measures.observed_endpoints_count,
            "http_observation_count": measures.http_observation_count,
            "javascript_reference_count": measures.javascript_reference_count,
            "new_hosts_count": measures.new_hosts_count,
            "new_services_count": measures.new_services_count,
            "new_endpoints_count": measures.new_endpoints_count,
            "new_surface_nodes_count": measures.new_surface_nodes_count,
            "new_surface_edges_count": measures.new_surface_edges_count,
            "new_surface_clusters_count": measures.new_surface_clusters_count,
            "new_surface_deltas_count": measures.new_surface_deltas_count,
            "new_graph_facts_count": measures.new_graph_facts_count,
            "new_search_documents_count": measures.new_search_documents_count,
            "information_gain_score": score.information_gain_score,
            "score_version": score.score_version,
            "score_breakdown": score.score_breakdown,
            "created_at": now,
            "updated_at": now,
        }

    @classmethod
    def _record_from_outcome_row(cls, values: Mapping[str, Any]) -> ActionOutcomeRecord:
        measures = ActionOutcomeMeasures(
            raw_artifact_count=int(values.get("raw_artifact_count") or 0),
            raw_artifact_bytes=int(values.get("raw_artifact_bytes") or 0),
            observed_hosts_count=int(values.get("observed_hosts_count") or 0),
            observed_services_count=int(values.get("observed_services_count") or 0),
            observed_endpoints_count=int(values.get("observed_endpoints_count") or 0),
            http_observation_count=int(values.get("http_observation_count") or 0),
            javascript_reference_count=int(values.get("javascript_reference_count") or 0),
            new_hosts_count=values.get("new_hosts_count"),
            new_services_count=values.get("new_services_count"),
            new_endpoints_count=values.get("new_endpoints_count"),
            new_surface_nodes_count=values.get("new_surface_nodes_count"),
            new_surface_edges_count=values.get("new_surface_edges_count"),
            new_surface_clusters_count=values.get("new_surface_clusters_count"),
            new_surface_deltas_count=values.get("new_surface_deltas_count"),
            new_graph_facts_count=values.get("new_graph_facts_count"),
            new_search_documents_count=values.get("new_search_documents_count"),
            duration_ms=values.get("duration_ms"),
            error_count=int(values.get("error_count") or 0),
        )
        score = ActionOutcomeScore(
            information_gain_score=float(values.get("information_gain_score") or 0.0),
            score_version=values["score_version"],
            score_breakdown=dict(values.get("score_breakdown") or {}),
        )
        return cls._record_from_values(
            values=values,
            measures=measures,
            score=score,
        )

    @staticmethod
    def _record_from_values(
        *,
        values: Mapping[str, Any],
        measures: ActionOutcomeMeasures,
        score: ActionOutcomeScore,
    ) -> ActionOutcomeRecord:
        terminal_outcome = (
            TerminalOutcome(values["terminal_outcome"])
            if values.get("terminal_outcome") is not None
            else None
        )
        return ActionOutcomeRecord(
            outcome_id=values["id"],
            program_id=values["program_id"],
            campaign_id=values.get("campaign_id"),
            action_id=values["action_id"],
            job_id=values["job_id"],
            run_id=values["run_id"],
            capability_id=values["capability_id"],
            profile_id=values["profile_id"],
            node_id=values.get("node_id"),
            event_name=values.get("event_name"),
            correlation_id=values.get("correlation_id"),
            status=ExecutionStatus(values["status"]),
            terminal_outcome=terminal_outcome,
            attempt=int(values["attempt"]),
            target_count=values.get("target_count"),
            started_at=values.get("started_at"),
            finished_at=values.get("finished_at"),
            duration_ms=values.get("duration_ms"),
            error_count=int(values.get("error_count") or 0),
            error_message=values.get("error_message"),
            measures=measures,
            score=score,
            manual_interest=values.get("manual_interest"),
            manual_stop=values.get("manual_stop"),
            continued_by_followup=values.get("continued_by_followup"),
            report_created=values.get("report_created"),
            triage_outcome=values.get("triage_outcome"),
            created_at=values["created_at"],
            updated_at=values["updated_at"],
        )
