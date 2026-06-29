from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.producers.action_outcomes import ActionOutcomeGraphFactProducer

    return ActionOutcomeGraphFactProducer


def _action_outcome_row(**overrides):
    row = {
        "id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "action_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
        "capability_id": "web.http_probe",
        "profile_id": "passive-default",
        "node_id": "httpx",
        "event_name": "httpx.completed",
        "status": "completed",
        "terminal_outcome": "completed",
        "attempt": 1,
        "target_count": 3,
        "started_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        "duration_ms": 60_000,
        "error_count": 0,
        "raw_artifact_count": 2,
        "raw_artifact_bytes": 1024,
        "observed_hosts_count": 1,
        "observed_services_count": 1,
        "observed_endpoints_count": 4,
        "http_observation_count": 4,
        "javascript_reference_count": 1,
        "manual_interest": True,
        "manual_stop": None,
        "continued_by_followup": True,
        "report_created": False,
        "triage_outcome": None,
        "information_gain_score": 7.5,
        "score_version": "action-outcome-information-gain.v1",
        "before_surface_snapshot_id": uuid4(),
        "after_surface_snapshot_id": uuid4(),
        "updated_at": datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_action_outcome_producer_projects_experience_into_graph_features() -> None:
    ActionOutcomeGraphFactProducer = _symbols()
    row = _action_outcome_row()

    batch = ActionOutcomeGraphFactProducer().produce(row)

    assert batch is not None
    assert batch.program_id == row["program_id"]
    assert batch.produced_by == "action-outcome-memory"

    node_facts = {(fact.kind, fact.key) for fact in batch.facts if hasattr(fact, "kind")}
    assert ("Program", str(row["program_id"])) in node_facts
    assert ("ToolRun", str(row["run_id"])) in node_facts
    assert ("ActionOutcome", str(row["id"])) in node_facts
    assert ("CapabilityProfile", "web.http_probe:passive-default") in node_facts
    assert ("SurfaceSnapshot", str(row["before_surface_snapshot_id"])) in node_facts
    assert ("SurfaceSnapshot", str(row["after_surface_snapshot_id"])) in node_facts
    assert ("OutcomeFeature", "capability:web.http_probe") in node_facts
    assert ("OutcomeFeature", "profile:passive-default") in node_facts
    assert ("OutcomeFeature", "capability_profile:web.http_probe:passive-default") in node_facts
    assert ("OutcomeFeature", "surface_hosts_bucket:1") in node_facts
    assert ("OutcomeFeature", "surface_services_bucket:1") in node_facts
    assert ("OutcomeFeature", "surface_endpoints_bucket:2-5") in node_facts
    assert ("OutcomeFeature", "http_observation_bucket:2-5") in node_facts
    assert ("OutcomeFeature", "javascript_reference_bucket:1") in node_facts
    assert ("OutcomeFeature", "human_signal:manual_interest") in node_facts
    assert ("OutcomeFeature", "human_signal:continued_by_followup") in node_facts

    edge_facts = {
        (fact.src_kind, fact.edge_kind, fact.dst_kind)
        for fact in batch.facts
        if hasattr(fact, "edge_kind")
    }
    assert ("Program", "HAS_ACTION_OUTCOME", "ActionOutcome") in edge_facts
    assert ("ActionOutcome", "OUTCOME_OF_RUN", "ToolRun") in edge_facts
    assert ("ActionOutcome", "USED_CAPABILITY_PROFILE", "CapabilityProfile") in edge_facts
    assert ("ActionOutcome", "BEFORE_SURFACE_SNAPSHOT", "SurfaceSnapshot") in edge_facts
    assert ("ActionOutcome", "AFTER_SURFACE_SNAPSHOT", "SurfaceSnapshot") in edge_facts
    assert ("ActionOutcome", "HAS_OUTCOME_FEATURE", "OutcomeFeature") in edge_facts
    assert ("ToolRun", "USED_TOOL", "Tool") in edge_facts

    assert all(getattr(fact, "tool_run_id", None) == row["run_id"] for fact in batch.facts)


def test_action_outcome_producer_uses_generic_features_not_vulnerability_labels() -> None:
    ActionOutcomeGraphFactProducer = _symbols()
    batch = ActionOutcomeGraphFactProducer().produce(_action_outcome_row())
    rendered = repr(batch.model_dump(mode="json"))

    for forbidden in ("idor", "ssrf", "takeover", "auth bypass"):
        assert forbidden not in rendered.lower()
