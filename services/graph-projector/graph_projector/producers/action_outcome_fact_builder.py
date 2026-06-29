from __future__ import annotations

from typing import Any

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .action_outcome_features import outcome_features
from .action_outcome_projection import ActionOutcomeProjection

PRODUCER_NAME = "action-outcome-memory"



def build_action_outcome_graph_fact_batch(
    projection: ActionOutcomeProjection,
    *,
    parser_version: str,
) -> GraphFactBatch:
    lineage = action_outcome_lineage(projection)
    facts: list[GraphNodeFact | GraphEdgeFact] = [
        _program_node(projection, lineage),
        _tool_run_node(projection, lineage),
        _capability_profile_node(projection, lineage),
        _action_outcome_node(projection, lineage),
        _edge(projection, lineage, "Program", str(projection.program_id), "HAS_ACTION_OUTCOME", "ActionOutcome", str(projection.outcome_id)),
        _edge(projection, lineage, "ActionOutcome", str(projection.outcome_id), "OUTCOME_OF_RUN", "ToolRun", str(projection.run_id)),
        _edge(
            projection,
            lineage,
            "ActionOutcome",
            str(projection.outcome_id),
            "USED_CAPABILITY_PROFILE",
            "CapabilityProfile",
            projection.profile_key,
        ),
    ]
    facts.extend(_tool_facts(projection, lineage))
    facts.extend(_surface_snapshot_facts(projection, lineage))
    facts.extend(_outcome_feature_facts(projection, lineage))
    return GraphFactBatch(
        program_id=projection.program_id,
        produced_by=PRODUCER_NAME,
        parser_version=parser_version,
        facts=facts,
    )



def action_outcome_lineage(projection: ActionOutcomeProjection) -> dict[str, Any]:
    return {
        "program_id": projection.program_id,
        "producer": PRODUCER_NAME,
        "source_artifact_id": None,
        "tool_run_id": projection.run_id,
        "confidence": 1.0,
    }



def _program_node(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="Program",
        key=str(projection.program_id),
        properties={"program_id": str(projection.program_id)},
    )



def _tool_run_node(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="ToolRun",
        key=str(projection.run_id),
        properties={
            "tool_run_id": str(projection.run_id),
            "job_id": projection.job_id,
            "action_id": projection.action_id,
            "campaign_id": projection.campaign_id,
            "status": projection.status,
            "terminal_outcome": projection.terminal_outcome,
            "started_at": projection.started_at,
            "finished_at": projection.finished_at,
        },
    )



def _capability_profile_node(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="CapabilityProfile",
        key=projection.profile_key,
        properties={
            "capability_id": projection.capability_id,
            "profile_id": projection.profile_id,
            "profile_key": projection.profile_key,
        },
    )



def _action_outcome_node(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> GraphNodeFact:
    return GraphNodeFact(
        **lineage,
        kind="ActionOutcome",
        key=str(projection.outcome_id),
        properties={
            "outcome_id": str(projection.outcome_id),
            "action_id": projection.action_id,
            "job_id": projection.job_id,
            "run_id": str(projection.run_id),
            "campaign_id": projection.campaign_id,
            "capability_id": projection.capability_id,
            "profile_id": projection.profile_id,
            "node_id": projection.node_id,
            "event_name": projection.event_name,
            "status": projection.status,
            "terminal_outcome": projection.terminal_outcome,
            "target_count": projection.target_count,
            "duration_ms": projection.duration_ms,
            "error_count": projection.error_count,
            "raw_artifact_count": projection.raw_artifact_count,
            "http_observation_count": projection.http_observation_count,
            "javascript_reference_count": projection.javascript_reference_count,
            "observation_count": projection.observation_count,
            "observed_hosts_count": projection.observed_hosts_count,
            "observed_services_count": projection.observed_services_count,
            "observed_endpoints_count": projection.observed_endpoints_count,
            "information_gain_score": projection.information_gain_score,
            "score_version": projection.score_version,
            "before_surface_snapshot_id": projection.before_surface_snapshot_id,
            "after_surface_snapshot_id": projection.after_surface_snapshot_id,
            "manual_interest": projection.manual_interest,
            "manual_stop": projection.manual_stop,
            "continued_by_followup": projection.continued_by_followup,
            "report_created": projection.report_created,
            "triage_outcome": projection.triage_outcome,
            "finished_at": projection.finished_at,
            "updated_at": projection.updated_at,
        },
    )



def _tool_facts(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> list[GraphNodeFact | GraphEdgeFact]:
    if not projection.node_id:
        return []
    return [
        GraphNodeFact(
            **lineage,
            kind="Tool",
            key=projection.node_id,
            properties={"tool_id": projection.node_id, "event_name": projection.event_name},
        ),
        _edge(projection, lineage, "ToolRun", str(projection.run_id), "USED_TOOL", "Tool", projection.node_id),
    ]



def _surface_snapshot_facts(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> list[GraphNodeFact | GraphEdgeFact]:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    for edge_kind, snapshot_id in (
        ("BEFORE_SURFACE_SNAPSHOT", projection.before_surface_snapshot_id),
        ("AFTER_SURFACE_SNAPSHOT", projection.after_surface_snapshot_id),
    ):
        if not snapshot_id:
            continue
        facts.extend(
            [
                GraphNodeFact(
                    **lineage,
                    kind="SurfaceSnapshot",
                    key=snapshot_id,
                    properties={"snapshot_id": snapshot_id},
                ),
                _edge(projection, lineage, "ActionOutcome", str(projection.outcome_id), edge_kind, "SurfaceSnapshot", snapshot_id),
            ]
        )
    return facts



def _outcome_feature_facts(projection: ActionOutcomeProjection, lineage: dict[str, Any]) -> list[GraphNodeFact | GraphEdgeFact]:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    for feature_type, feature_value in outcome_features(projection):
        feature_key = f"{feature_type}:{feature_value}"
        facts.extend(
            [
                GraphNodeFact(
                    **lineage,
                    kind="OutcomeFeature",
                    key=feature_key,
                    properties={
                        "feature_type": feature_type,
                        "feature_value": str(feature_value),
                    },
                ),
                _edge(
                    projection,
                    lineage,
                    "ActionOutcome",
                    str(projection.outcome_id),
                    "HAS_OUTCOME_FEATURE",
                    "OutcomeFeature",
                    feature_key,
                ),
            ]
        )
    return facts



def _edge(
    projection: ActionOutcomeProjection,
    lineage: dict[str, Any],
    src_kind: str,
    src_key: str,
    edge_kind: str,
    dst_kind: str,
    dst_key: str,
) -> GraphEdgeFact:
    return GraphEdgeFact(
        **lineage,
        src_kind=src_kind,
        src_key=src_key,
        edge_kind=edge_kind,
        dst_kind=dst_kind,
        dst_key=dst_key,
    )
