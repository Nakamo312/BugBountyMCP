"""PostgreSQL read model for dashboard workbench graph DTOs."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, desc, select

from api.application.workbench import (
    WorkbenchActionAffordanceList,
    WorkbenchEntityMemory,
    WorkbenchEntityProfile,
    WorkbenchGraph,
    WorkbenchLens,
    workbench_read_boundary,
)
from api.infrastructure.adapters.orm import (
    agent_action_proposals,
    research_hypotheses,
    research_hypothesis_evidence,
    research_hypothesis_events,
    research_hypothesis_score_history,
    research_signals,
)
from api.infrastructure.workbench_action import (
    action_entity_actions,
    action_entity_memory_from_graph,
    action_entity_profile_from_graph,
    build_action_lens_graph,
    is_action_entity_key,
)
from api.infrastructure.workbench_action_rows import (
    _approval_decisions_for_actions,
    _approval_requests_for_actions,
    _artifacts_for_outcomes,
    _feedback_for_actions,
    _jobs_for_actions,
    _outcomes_for_actions,
    _policy_decisions_for_actions,
    _recent_action_requests_for_program,
    _recent_action_targets_for_program,
    _recent_outcomes_for_program,
    _runs_for_jobs,
    _targets_for_actions,
)
from api.infrastructure.workbench_components import (
    build_component_lens_graph,
    component_entity_actions,
    component_entity_memory,
    component_entity_profile,
    _component_items_for_run,
    _is_component_entity_key,
    _latest_component_analysis,
)
from api.infrastructure.workbench_coverage import (
    build_coverage_lens_graph,
    coverage_entity_memory_from_graph,
    coverage_entity_profile_from_graph,
    is_coverage_entity_key,
)
from api.infrastructure.workbench_hypothesis import (
    build_hypothesis_lens_graph,
    hypothesis_entity_actions,
    hypothesis_entity_memory_from_graph,
    hypothesis_entity_profile_from_graph,
    is_hypothesis_entity_key,
)
from api.infrastructure.workbench_memory import build_memory_lens_graph
from api.infrastructure.workbench_surface import (
    build_surface_lens_graph,
    latest_surface_snapshot,
    surface_deltas_for_snapshot,
    surface_entity_actions,
    surface_entity_memory,
    surface_entity_profile,
    surface_nodes_for_snapshot,
)

_HYPOTHESIS_COLUMNS = (
    research_hypotheses.c.id.label("hypothesis_id"),
    research_hypotheses.c.program_id,
    research_hypotheses.c.hypothesis_type,
    research_hypotheses.c.hypothesis_fingerprint,
    research_hypotheses.c.status,
    research_hypotheses.c.state_version,
    research_hypotheses.c.priority_score,
    research_hypotheses.c.confidence,
    research_hypotheses.c.severity_guess,
    research_hypotheses.c.safety_level,
    research_hypotheses.c.score_version,
    research_hypotheses.c.inputs_hash,
    research_hypotheses.c.source_signal_fingerprints,
    research_hypotheses.c.duplicate_of_hypothesis_id,
    research_hypotheses.c.first_seen,
    research_hypotheses.c.last_seen,
    research_hypotheses.c.updated_at,
)

_HYPOTHESIS_EVIDENCE_COLUMNS = (
    research_hypothesis_evidence.c.id.label("evidence_id"),
    research_hypothesis_evidence.c.hypothesis_id,
    research_hypothesis_evidence.c.ref_type,
    research_hypothesis_evidence.c.ref_id,
    research_hypothesis_evidence.c.field_path,
    research_hypothesis_evidence.c.role,
    research_hypothesis_evidence.c.claim_type,
    research_hypothesis_evidence.c.claim,
    research_hypothesis_evidence.c.evidence_fingerprint,
    research_hypothesis_evidence.c.safe_excerpt,
    research_hypothesis_evidence.c.safe_excerpt_truncated,
    research_hypothesis_evidence.c.evidence_source,
    research_hypothesis_evidence.c.sanitizer_version,
    research_hypothesis_evidence.c.redaction_policy_version,
    research_hypothesis_evidence.c.sensitivity_level,
    research_hypothesis_evidence.c.redaction_rules_triggered,
    research_hypothesis_evidence.c.safe_for_search,
    research_hypothesis_evidence.c.safe_for_llm,
    research_hypothesis_evidence.c.created_at,
)

_RESEARCH_SIGNAL_COLUMNS = (
    research_signals.c.id.label("signal_id"),
    research_signals.c.program_id,
    research_signals.c.producer_run_id,
    research_signals.c.signal_type,
    research_signals.c.signal_version,
    research_signals.c.rule_id,
    research_signals.c.rule_version,
    research_signals.c.asset_type,
    research_signals.c.asset_id,
    research_signals.c.observation_id,
    research_signals.c.evidence_fingerprint,
    research_signals.c.confidence,
    research_signals.c.payload_json,
    research_signals.c.created_at,
)

_HYPOTHESIS_EVENT_COLUMNS = (
    research_hypothesis_events.c.id.label("event_id"),
    research_hypothesis_events.c.hypothesis_id,
    research_hypothesis_events.c.event_type,
    research_hypothesis_events.c.aggregate_version,
    research_hypothesis_events.c.actor,
    research_hypothesis_events.c.reason,
    research_hypothesis_events.c.payload_json,
    research_hypothesis_events.c.created_at,
)

_HYPOTHESIS_SCORE_COLUMNS = (
    research_hypothesis_score_history.c.id.label("score_id"),
    research_hypothesis_score_history.c.hypothesis_id,
    research_hypothesis_score_history.c.score_version,
    research_hypothesis_score_history.c.priority_score,
    research_hypothesis_score_history.c.confidence,
    research_hypothesis_score_history.c.severity_guess,
    research_hypothesis_score_history.c.safety_level,
    research_hypothesis_score_history.c.inputs_hash,
    research_hypothesis_score_history.c.factors_json,
    research_hypothesis_score_history.c.created_at,
)

_HYPOTHESIS_PROPOSAL_COLUMNS = (
    agent_action_proposals.c.id.label("proposal_id"),
    agent_action_proposals.c.program_id,
    agent_action_proposals.c.campaign_id,
    agent_action_proposals.c.task_id,
    agent_action_proposals.c.source_message_id,
    agent_action_proposals.c.agent_key,
    agent_action_proposals.c.proposal_key,
    agent_action_proposals.c.proposal_type,
    agent_action_proposals.c.status,
    agent_action_proposals.c.title,
    agent_action_proposals.c.summary,
    agent_action_proposals.c.rationale,
    agent_action_proposals.c.capability_id,
    agent_action_proposals.c.profile_id,
    agent_action_proposals.c.priority,
    agent_action_proposals.c.expected_gain,
    agent_action_proposals.c.action_intent,
    agent_action_proposals.c.action_params,
    agent_action_proposals.c.context_refs,
    agent_action_proposals.c.metadata,
    agent_action_proposals.c.accepted_action_id,
    agent_action_proposals.c.review_feedback,
    agent_action_proposals.c.created_at,
    agent_action_proposals.c.updated_at,
)



class WorkbenchGraphStore:
    """Route workbench reads to lens-specific read-model builders."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def surface_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        return await build_surface_lens_graph(
            self.session_factory,
            program_id=program_id,
            seed=seed,
            depth=depth,
            limit=limit,
        )

    async def component_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        return await build_component_lens_graph(
            self.session_factory,
            program_id=program_id,
            seed=seed,
            depth=depth,
            limit=limit,
        )

    async def memory_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        async with self.session_factory() as session:
            outcomes = await _recent_outcomes_for_program(session, program_id, limit=max(1, min(limit, 250)))
            artifacts = await _artifacts_for_outcomes(
                session,
                [outcome["run_id"] for outcome in outcomes],
                program_id=program_id,
                limit=max(1, min(limit * 3, 750)),
            )
        return build_memory_lens_graph(
            program_id=program_id,
            outcomes=outcomes,
            artifacts=artifacts,
            seed=seed,
            depth=depth,
            limit=max(1, min(limit, 500)),
        )

    async def action_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        bounded_limit = max(1, min(limit, 500))
        async with self.session_factory() as session:
            action_rows = await _recent_action_requests_for_program(session, program_id, limit=bounded_limit)
            action_ids = [row["action_id"] for row in action_rows]
            target_rows = await _targets_for_actions(session, action_ids, limit=bounded_limit * 4)
            policy_rows = await _policy_decisions_for_actions(session, action_ids, limit=bounded_limit * 2)
            approval_request_rows = await _approval_requests_for_actions(session, action_ids, limit=bounded_limit * 2)
            approval_decision_rows = await _approval_decisions_for_actions(session, action_ids, limit=bounded_limit * 2)
            job_rows = await _jobs_for_actions(session, action_ids, limit=bounded_limit * 2)
            run_rows = await _runs_for_jobs(session, [row["job_id"] for row in job_rows], limit=bounded_limit * 3)
            outcome_rows = await _outcomes_for_actions(session, program_id, action_ids, limit=bounded_limit * 3)
            feedback_rows = await _feedback_for_actions(session, program_id, action_ids, limit=bounded_limit * 3)
        return build_action_lens_graph(
            program_id=program_id,
            actions=action_rows,
            targets=target_rows,
            policy_decisions=policy_rows,
            approval_requests=approval_request_rows,
            approval_decisions=approval_decision_rows,
            jobs=job_rows,
            runs=run_rows,
            outcomes=outcome_rows,
            feedback_events=feedback_rows,
            seed=seed,
            depth=depth,
            limit=bounded_limit,
        )

    async def hypothesis_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        bounded_limit = max(1, min(limit, 500))
        async with self.session_factory() as session:
            hypothesis_rows = await _recent_hypotheses_for_program(session, program_id, limit=bounded_limit)
            hypothesis_ids = [row["hypothesis_id"] for row in hypothesis_rows]
            evidence_rows = await _hypothesis_evidence_for_hypotheses(session, hypothesis_ids, limit=bounded_limit * 4)
            signal_fingerprints = _signal_fingerprints_from_hypotheses(hypothesis_rows)
            signal_rows = await _research_signals_for_fingerprints(session, program_id, signal_fingerprints, limit=bounded_limit * 3)
            event_rows = await _hypothesis_events_for_hypotheses(session, hypothesis_ids, limit=bounded_limit * 3)
            score_rows = await _hypothesis_scores_for_hypotheses(session, hypothesis_ids, limit=bounded_limit * 3)
            proposal_rows = await _hypothesis_proposals_for_program(session, program_id, limit=bounded_limit * 2)
        return build_hypothesis_lens_graph(
            program_id=program_id,
            hypotheses=hypothesis_rows,
            evidence_rows=evidence_rows,
            signal_rows=signal_rows,
            event_rows=event_rows,
            score_rows=score_rows,
            proposal_rows=proposal_rows,
            seed=seed,
            depth=depth,
            limit=bounded_limit,
        )

    async def coverage_graph(
        self,
        *,
        program_id: UUID,
        seed: str | None = None,
        depth: int = 1,
        limit: int = 250,
    ) -> WorkbenchGraph | None:
        async with self.session_factory() as session:
            snapshot = await latest_surface_snapshot(session, program_id)
            if snapshot is None:
                return None
            node_rows = await surface_nodes_for_snapshot(session, program_id, snapshot["id"], limit=max(1, min(limit * 2, 1000)))
            delta_by_subject = await surface_deltas_for_snapshot(session, program_id, snapshot["id"])
            component_run = await _latest_component_analysis(session, program_id)
            component_items = (
                await _component_items_for_run(session, component_run["id"], limit=max(1, min(limit, 500)))
                if component_run is not None
                else []
            )
            action_rows = await _recent_action_targets_for_program(session, program_id, limit=max(1, min(limit * 2, 1000)))
            outcomes = await _recent_outcomes_for_program(session, program_id, limit=max(1, min(limit * 2, 1000)))
        return build_coverage_lens_graph(
            program_id=program_id,
            snapshot=snapshot,
            node_rows=node_rows,
            delta_by_subject=delta_by_subject,
            component_run=component_run,
            component_items=component_items,
            action_rows=action_rows,
            outcome_rows=outcomes,
            seed=seed,
            depth=depth,
            limit=max(1, min(limit, 500)),
        )

    async def entity_profile(self, *, program_id: UUID, entity_key: str) -> WorkbenchEntityProfile | None:
        if is_hypothesis_entity_key(entity_key):
            graph = await self.hypothesis_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return hypothesis_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if is_action_entity_key(entity_key):
            graph = await self.action_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return action_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if is_coverage_entity_key(entity_key):
            graph = await self.coverage_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return coverage_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if _is_component_entity_key(entity_key):
            return await component_entity_profile(self.session_factory, program_id=program_id, entity_key=entity_key)
        return await surface_entity_profile(self.session_factory, program_id=program_id, entity_key=entity_key)

    async def entity_actions(
        self,
        *,
        program_id: UUID,
        entity_key: str,
        limit: int = 10,
    ) -> WorkbenchActionAffordanceList | None:
        if is_hypothesis_entity_key(entity_key):
            graph = await self.hypothesis_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None or hypothesis_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph) is None:
                return None
            return hypothesis_entity_actions(program_id=program_id, entity_key=entity_key)
        if is_action_entity_key(entity_key):
            graph = await self.action_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None or action_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph) is None:
                return None
            return action_entity_actions(program_id=program_id, entity_key=entity_key)
        if is_coverage_entity_key(entity_key):
            graph = await self.coverage_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            profile = coverage_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
            if profile is None:
                return None
            return WorkbenchActionAffordanceList(
                program_id=program_id,
                entity_key=entity_key,
                actions=[],
                boundary=workbench_read_boundary(surface="coverage_read_only_no_action_affordances"),
            )
        if _is_component_entity_key(entity_key):
            return await component_entity_actions(self.session_factory, program_id=program_id, entity_key=entity_key, limit=limit)
        return await surface_entity_actions(self.session_factory, program_id=program_id, entity_key=entity_key, limit=limit)

    async def entity_memory(
        self,
        *,
        program_id: UUID,
        entity_key: str,
        limit: int = 20,
    ) -> WorkbenchEntityMemory | None:
        if is_hypothesis_entity_key(entity_key):
            graph = await self.hypothesis_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return hypothesis_entity_memory_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if is_action_entity_key(entity_key):
            graph = await self.action_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return action_entity_memory_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if is_coverage_entity_key(entity_key):
            graph = await self.coverage_graph(program_id=program_id, seed=entity_key, depth=1, limit=100)
            if graph is None:
                return None
            return coverage_entity_memory_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
        if _is_component_entity_key(entity_key):
            return await component_entity_memory(self.session_factory, program_id=program_id, entity_key=entity_key)
        return await surface_entity_memory(self.session_factory, program_id=program_id, entity_key=entity_key, limit=limit)


async def _recent_hypotheses_for_program(session: Any, program_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_HYPOTHESIS_COLUMNS)
        .where(research_hypotheses.c.program_id == bindparam("program_id"))
        .order_by(
            desc(research_hypotheses.c.priority_score),
            desc(research_hypotheses.c.updated_at),
            research_hypotheses.c.id.desc(),
        )
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


async def _hypothesis_evidence_for_hypotheses(
    session: Any,
    hypothesis_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not hypothesis_ids:
        return []
    statement = (
        select(*_HYPOTHESIS_EVIDENCE_COLUMNS)
        .where(research_hypothesis_evidence.c.hypothesis_id.in_(hypothesis_ids))
        .order_by(
            research_hypothesis_evidence.c.hypothesis_id.asc(),
            research_hypothesis_evidence.c.role.asc(),
            research_hypothesis_evidence.c.created_at.desc(),
        )
        .limit(max(limit, 1))
    )
    result = await session.execute(statement)
    return list(result.mappings().all())


async def _research_signals_for_fingerprints(
    session: Any,
    program_id: UUID,
    fingerprints: list[str],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not fingerprints:
        return []
    statement = (
        select(*_RESEARCH_SIGNAL_COLUMNS)
        .where(research_signals.c.program_id == bindparam("program_id"))
        .where(research_signals.c.evidence_fingerprint.in_(fingerprints))
        .order_by(desc(research_signals.c.created_at), research_signals.c.id.desc())
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


async def _hypothesis_events_for_hypotheses(
    session: Any,
    hypothesis_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not hypothesis_ids:
        return []
    statement = (
        select(*_HYPOTHESIS_EVENT_COLUMNS)
        .where(research_hypothesis_events.c.hypothesis_id.in_(hypothesis_ids))
        .order_by(
            research_hypothesis_events.c.hypothesis_id.asc(),
            research_hypothesis_events.c.aggregate_version.asc(),
            research_hypothesis_events.c.created_at.asc(),
        )
        .limit(max(limit, 1))
    )
    result = await session.execute(statement)
    return list(result.mappings().all())


async def _hypothesis_scores_for_hypotheses(
    session: Any,
    hypothesis_ids: list[UUID],
    *,
    limit: int,
) -> list[Mapping[str, Any]]:
    if not hypothesis_ids:
        return []
    statement = (
        select(*_HYPOTHESIS_SCORE_COLUMNS)
        .where(research_hypothesis_score_history.c.hypothesis_id.in_(hypothesis_ids))
        .order_by(
            research_hypothesis_score_history.c.hypothesis_id.asc(),
            desc(research_hypothesis_score_history.c.created_at),
        )
        .limit(max(limit, 1))
    )
    result = await session.execute(statement)
    return list(result.mappings().all())


async def _hypothesis_proposals_for_program(session: Any, program_id: UUID, *, limit: int) -> list[Mapping[str, Any]]:
    statement = (
        select(*_HYPOTHESIS_PROPOSAL_COLUMNS)
        .where(agent_action_proposals.c.program_id == bindparam("program_id"))
        .order_by(desc(agent_action_proposals.c.created_at), agent_action_proposals.c.id.desc())
        .limit(max(limit, 1))
    )
    result = await session.execute(statement, {"program_id": program_id})
    return list(result.mappings().all())


def _signal_fingerprints_from_hypotheses(hypotheses: list[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for row in hypotheses:
        fingerprints = row.get("source_signal_fingerprints")
        if not isinstance(fingerprints, (list, tuple)):
            continue
        for fingerprint in fingerprints:
            text = str(fingerprint).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
    return values
