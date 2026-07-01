from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from api.infrastructure import workbench as workbench_store
from api.infrastructure import workbench_components, workbench_surface


def _row(**overrides):
    data = {
        "id": uuid4(),
        "node_type": "endpoint",
        "ref_type": "http_observation",
        "ref_id": "obs-1",
        "node_fingerprint": "n" * 64,
        "feature_fingerprint": "f" * 64,
        "host": "example.com",
        "path": "/api/users/123",
        "route_template": "/api/users/{id}",
        "method": "GET",
        "status_code": 200,
        "content_type": "application/json",
        "features_json": {"source": {"source_tool": "httpx", "ref_type": "http_observation", "ref_id": "obs-1"}},
        "safe_for_search": True,
        "first_seen": datetime(2026, 6, 30, tzinfo=timezone.utc),
        "last_seen": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return data


def test_workbench_node_mapper_builds_frontend_entity_without_raw_database_shape() -> None:
    row = _row()

    node = workbench_surface._node_from_row(row, {row["node_fingerprint"]: "added"})

    assert node.id == f"node:{row['id']}"
    assert node.entity_key == f"surface:endpoint:{row['node_fingerprint']}"
    assert node.label == "GET /api/users/{id}"
    assert node.caption == "example.com, application/json, httpx"
    assert node.properties["node_fingerprint"] == row["node_fingerprint"]
    assert node.evidence_refs == [{"type": "http_observation", "id": "obs-1"}]
    assert node.staleness == "fresh"
    assert "features" in node.metadata


def test_workbench_node_mapper_drops_features_when_node_is_not_search_safe() -> None:
    row = _row(safe_for_search=False, features_json={"secretish": "must-not-leak"})

    node = workbench_surface._node_from_row(row, {})

    assert node.metadata == {"features": {}}
    assert node.confidence == 0.5


def test_workbench_edge_mapper_exposes_relationship_not_cypher_shape() -> None:
    edge_id = uuid4()
    src_id = uuid4()
    dst_id = uuid4()
    row = {
        "id": edge_id,
        "src_node_id": src_id,
        "dst_node_id": dst_id,
        "edge_type": "HAS_ROUTE_SHAPE",
        "weight": 1.0,
        "edge_fingerprint": "e" * 64,
        "evidence_json": {"basis": "shared_route_fingerprint"},
        "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }

    edge = workbench_surface._edge_from_row(row, {row["edge_fingerprint"]: "changed"})

    assert edge.id == f"edge:{edge_id}"
    assert edge.source == f"node:{src_id}"
    assert edge.target == f"node:{dst_id}"
    assert edge.relationship_type == "HAS_ROUTE_SHAPE"
    assert edge.label == "has route shape"
    assert edge.delta_state == "changed"
    assert edge.source_projection == "surface_map"



def test_workbench_surface_adds_ui_grouping_when_persisted_edges_are_absent() -> None:
    row_a = _row(host="example.com", path="/api/users/1", route_template="/api/users/{id}")
    row_b = _row(host="example.com", path="/api/orders/1", route_template="/api/orders/{id}")

    group_nodes, group_edges = workbench_surface._surface_ui_grouping([row_a, row_b])

    assert {node.node_type for node in group_nodes} == {"host", "route_family"}
    assert any(node.label == "example.com" for node in group_nodes)
    assert any(node.label == "/api/*" for node in group_nodes)
    assert {edge.relationship_type for edge in group_edges} == {"HAS_ROUTE_FAMILY", "CONTAINS_SURFACE_NODE"}
    assert all(edge.source_projection == "surface_map_ui_grouping" for edge in group_edges)


def test_workbench_surface_entity_lookup_has_sqlalchemy_or_import() -> None:
    source = workbench_surface.__loader__.get_source(workbench_surface.__name__)

    assert "from sqlalchemy import bindparam, desc, func, or_, select" in source
    assert ".where(or_(*predicates))" in source

def test_workbench_graph_store_delegates_surface_map_tables_to_surface_module() -> None:
    main_source = workbench_store.__loader__.get_source(workbench_store.__name__)
    surface_source = workbench_surface.__loader__.get_source(workbench_surface.__name__)

    assert "build_surface_lens_graph" in main_source
    assert "surface_nodes.c" not in main_source
    assert "surface_edges.c" not in main_source
    assert "surface_nodes" in surface_source
    assert "surface_edges" in surface_source
    assert "surface_deltas" in surface_source
    assert "neo4j" not in surface_source.lower()
    assert "cypher" not in surface_source.lower()
    assert "execute_tool" not in surface_source


def _component_run(**overrides):
    data = {
        "id": uuid4(),
        "program_id": uuid4(),
        "snapshot_id": uuid4(),
        "previous_snapshot_id": None,
        "algorithm": "surface-component-report",
        "algorithm_version": "surface-component-analysis-v1",
        "report_fingerprint": "r" * 64,
        "stats_json": {"component_count": 1},
        "settings_json": {"limit": 10},
        "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return data


def _component_item(**overrides):
    data = {
        "component_id": 7,
        "node_count": 9,
        "changed_node_count": 2,
        "structural_pressure_score": 80,
        "drift_score": 30,
        "bridge_pressure_score": 50,
        "outlier_score": 60,
        "coverage_score": 20,
        "exploration_priority_score": 70,
        "action_candidate_count": 1,
        "metrics_json": {"profile": {"component_id": 7}},
        "action_candidates_json": [
            {
                "capability_id": "katana",
                "profile_id": "safe-crawl",
                "candidate_score": 61,
                "score_features": {"positive_rate": 0.4},
            }
        ],
    }
    data.update(overrides)
    return data


def test_workbench_component_mapper_builds_analysis_component_candidate_graph_without_verdict_semantics() -> None:
    run = _component_run()
    item = _component_item()

    nodes, edges = workbench_components._component_graph_from_rows(program_id=run["program_id"], run=run, items=[item], seed=None)

    assert [node.node_type for node in nodes] == [
        "surface_component_analysis_run",
        "surface_component",
        "surface_component_action_candidate",
    ]
    component = nodes[1]
    candidate = nodes[2]
    assert component.entity_key == f"surface-component:{run['id']}:7"
    assert component.metadata["signals"]["exploration_pressure"] == 70
    assert component.metadata["signal_contract"]["calibration_status"] == "uncalibrated"
    assert candidate.label == "katana / safe-crawl"
    assert candidate.confidence == 0.61
    assert {edge.relationship_type for edge in edges} == {"HAS_COMPONENT", "SUGGESTS_ACTION"}
    assert all(edge.source_projection == "surface_component_analysis" for edge in edges)


def test_workbench_component_affordance_is_candidate_not_direct_execution() -> None:
    action = workbench_components._component_candidate_affordance(_component_item()["action_candidates_json"][0], 0)

    assert action.catalog_id == "katana.safe-crawl"
    assert action.enabled is False
    assert action.disabled_reasons == ["candidate_only_requires_action_service_submission"]
    assert action.expected_delta == [{"kind": "candidate_signal_features", "features": {"positive_rate": 0.4}}]


def test_workbench_main_store_delegates_component_lens_instead_of_becoming_lens_dump() -> None:
    main_source = workbench_store.__loader__.get_source(workbench_store.__name__)
    component_source = workbench_components.__loader__.get_source(workbench_components.__name__)

    assert len(main_source.splitlines()) < 1800
    assert "build_component_lens_graph" in main_source
    assert "def _component_node_from_row" not in main_source
    assert "def _component_node_from_row" in component_source
    assert "surface_component_analysis_items" in component_source


def _outcome(**overrides):
    now = datetime(2026, 6, 30, tzinfo=timezone.utc)
    data = {
        "outcome_id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "action_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "node_id": "surface:endpoint:" + "f" * 64,
        "event_name": "crawl.completed",
        "status": "completed",
        "terminal_outcome": "completed",
        "attempt": 1,
        "duration_ms": 1200,
        "error_count": 0,
        "raw_artifact_count": 1,
        "observed_hosts_count": 1,
        "observed_services_count": 1,
        "observed_endpoints_count": 3,
        "http_observation_count": 8,
        "javascript_reference_count": 0,
        "new_hosts_count": 0,
        "new_services_count": 0,
        "new_endpoints_count": 2,
        "new_surface_nodes_count": 4,
        "new_surface_edges_count": 3,
        "new_surface_clusters_count": 0,
        "new_surface_deltas_count": 2,
        "new_graph_facts_count": 5,
        "new_search_documents_count": 6,
        "manual_interest": True,
        "manual_stop": False,
        "continued_by_followup": None,
        "report_created": False,
        "triage_outcome": None,
        "information_gain_score": 7.5,
        "score_breakdown": {"delta": 1.0},
        "created_at": now,
        "finished_at": now,
    }
    data.update(overrides)
    return data


def _artifact(**overrides):
    data = {
        "artifact_id": uuid4(),
        "run_id": uuid4(),
        "job_id": uuid4(),
        "node_id": "surface:endpoint:" + "f" * 64,
        "event_name": "crawl.completed",
        "artifact_type": "http_snapshot",
        "sha256": "a" * 64,
        "size_bytes": 123,
        "storage_size_bytes": 100,
        "content_encoding": "identity",
        "retention_class": "program_lifetime",
        "raw_safe_for_llm": False,
        "sanitized_safe_for_llm": True,
        "parser_name": "http",
        "parser_version": "1",
        "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return data


def test_workbench_memory_lens_builds_temporal_graph_without_raw_artifact_body() -> None:
    from api.infrastructure.workbench_memory import build_memory_lens_graph

    program_id = uuid4()
    outcome = _outcome(program_id=program_id)
    artifact = _artifact(run_id=outcome["run_id"])

    graph = build_memory_lens_graph(
        program_id=program_id,
        outcomes=[outcome],
        artifacts=[artifact],
        seed=None,
        depth=1,
        limit=50,
    )

    assert graph.lens.value == "memory"
    assert graph.boundary["surface"] == "memory_lens_from_action_outcomes"
    assert graph.counts["outcomes"] == 1
    assert graph.counts["artifacts"] == 1
    assert {
        "memory_program_summary",
        "memory_day_summary",
        "memory_campaign_summary",
        "action_run_group",
        "action_run",
        "observation",
        "delta",
        "artifact_ref",
    }.issubset({node.node_type for node in graph.nodes})
    artifact_node = next(node for node in graph.nodes if node.node_type == "artifact_ref")
    assert "storage_uri" not in artifact_node.properties
    assert "preview" not in artifact_node.properties
    assert any(edge.source_projection == "action_outcome_memory" for edge in graph.edges)


def test_workbench_entity_memory_tree_adds_day_campaign_action_observation_delta_nodes() -> None:
    from api.infrastructure.workbench_memory import build_entity_memory_summaries, build_entity_memory_tree

    outcome = _outcome()
    tree = build_entity_memory_tree([outcome])
    summaries = build_entity_memory_summaries([outcome], [_artifact(run_id=outcome["run_id"])])

    assert [node["kind"] for node in tree] == ["day_summary", "campaign_summary", "action", "run", "observation", "delta"]
    assert summaries[0]["kind"] == "entity_action_memory_summary"
    assert summaries[0]["summary_is_truth"] is False
    assert summaries[0]["new_surface_nodes_total"] == 4


def test_workbench_coverage_lens_builds_lanes_gaps_and_suggestions_without_verdict_semantics() -> None:
    from api.infrastructure.workbench_coverage import build_coverage_lens_graph

    program_id = uuid4()
    snapshot_id = uuid4()
    checked = _row(
        id=uuid4(),
        node_type="endpoint",
        node_fingerprint="c" * 64,
        feature_fingerprint="d" * 64,
        route_template="/api/checked",
        path="/api/checked",
    )
    unchecked = _row(
        id=uuid4(),
        node_type="endpoint",
        node_fingerprint="u" * 64,
        feature_fingerprint="v" * 64,
        route_template="/api/unchecked",
        path="/api/unchecked",
    )
    run = _component_run(program_id=program_id, snapshot_id=snapshot_id)
    component = _component_item(component_id=3, coverage_score=20, changed_node_count=1, exploration_priority_score=75)
    outcome = _outcome(program_id=program_id, node_id=f"surface:endpoint:{checked['node_fingerprint']}")
    action = {
        "action_id": outcome["action_id"],
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "target": f"surface:endpoint:{checked['node_fingerprint']}",
        "status": "allowed",
        "target_status": "allowed",
        "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }

    graph = build_coverage_lens_graph(
        program_id=program_id,
        snapshot={"id": snapshot_id, "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc)},
        node_rows=[checked, unchecked],
        delta_by_subject={unchecked["node_fingerprint"]: "changed"},
        component_run=run,
        component_items=[component],
        action_rows=[action],
        outcome_rows=[outcome],
        seed=None,
        depth=1,
        limit=100,
    )

    assert graph.lens.value == "coverage"
    assert graph.boundary["surface"] == "coverage_lens_structural_read_model"
    assert graph.counts["checked_entities"] == 1
    assert graph.counts["unchecked_entities"] == 1
    assert graph.counts["component_gaps"] == 1
    assert {
        "coverage_overview",
        "coverage_lane",
        "capability_lane",
        "checked_entity",
        "coverage_gap",
        "component_coverage_gap",
        "suggested_next_context",
    }.issubset({node.node_type for node in graph.nodes})
    gap = next(node for node in graph.nodes if node.node_type == "coverage_gap")
    assert gap.properties["coverage_is_verdict"] is False
    assert gap.metadata["coverage_contract"]["not_semantics"] == "vulnerability/risk/severity/finding/verdict"
    assert "risk" not in gap.node_type
    assert any(edge.relationship_type == "SUGGESTS_NEXT_CONTEXT" for edge in graph.edges)
    assert all(edge.source_projection == "workbench_coverage" for edge in graph.edges)


def test_workbench_coverage_entity_profile_and_memory_are_read_only_fragments() -> None:
    from api.infrastructure.workbench_coverage import (
        build_coverage_lens_graph,
        coverage_entity_memory_from_graph,
        coverage_entity_profile_from_graph,
    )

    program_id = uuid4()
    snapshot_id = uuid4()
    row = _row(node_fingerprint="g" * 64, feature_fingerprint="h" * 64, route_template="/gap", path="/gap")
    entity_key = f"coverage-gap:{row['node_fingerprint']}"
    graph = build_coverage_lens_graph(
        program_id=program_id,
        snapshot={"id": snapshot_id, "created_at": datetime(2026, 6, 30, tzinfo=timezone.utc)},
        node_rows=[row],
        delta_by_subject={},
        component_run=None,
        component_items=[],
        action_rows=[],
        outcome_rows=[],
        seed=entity_key,
        depth=1,
        limit=100,
    )

    profile = coverage_entity_profile_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)
    memory = coverage_entity_memory_from_graph(program_id=program_id, entity_key=entity_key, graph=graph)

    assert profile is not None
    assert memory is not None
    assert profile.boundary["surface"] == "coverage_entity_profile"
    assert memory.boundary["surface"] == "coverage_entity_memory"
    assert memory.fragments[0]["summary_is_truth"] is False
    assert memory.summaries[0]["not_semantics"] == "vulnerability/risk/severity/finding/verdict"


def test_workbench_action_lens_builds_lifecycle_graph_without_execution_surface() -> None:
    from api.infrastructure.workbench_action import (
        action_entity_actions,
        action_entity_memory_from_graph,
        action_entity_profile_from_graph,
        build_action_lens_graph,
    )

    program_id = uuid4()
    action_id = uuid4()
    target_id = uuid4()
    policy_id = uuid4()
    approval_request_id = uuid4()
    approval_decision_id = uuid4()
    job_id = uuid4()
    run_id = uuid4()
    outcome_id = uuid4()
    feedback_id = uuid4()
    now = datetime(2026, 6, 30, tzinfo=timezone.utc)
    action = {
        "action_id": action_id,
        "catalog_entry_id": uuid4(),
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "requested_by": "human",
        "campaign_id": uuid4(),
        "correlation_id": uuid4(),
        "metadata": {},
        "status": "allowed",
        "request": {"kind": "tool_action", "targets": ["https://example.com"], "options": {"depth": 1}, "budget": {"seconds": 30}},
        "created_at": now,
        "updated_at": now,
    }
    target = {
        "target_id": target_id,
        "action_id": action_id,
        "target": "https://example.com/path?token=secret",
        "position": 0,
        "target_status": "allowed",
        "created_at": now,
    }
    policy = {
        "policy_decision_id": policy_id,
        "action_id": action_id,
        "status": "allowed",
        "reasons": ["Authorization: Bearer should-redact"],
        "allowed_targets": ["https://example.com"],
        "blocked_targets": [],
        "safety_level": "safe_recon",
        "metadata": {},
        "catalog_hash": "c" * 64,
        "created_at": now,
    }
    approval_request = {
        "approval_request_id": approval_request_id,
        "action_id": action_id,
        "policy_decision_id": policy_id,
        "status": "approved",
        "reason": "operator approved",
        "requested_by": "policy",
        "created_at": now,
        "decided_at": now,
    }
    approval_decision = {
        "approval_decision_id": approval_decision_id,
        "approval_request_id": approval_request_id,
        "action_id": action_id,
        "decision": "approved",
        "decided_by": "human",
        "reason": "ok",
        "metadata": {},
        "created_at": now,
    }
    job = {
        "job_id": job_id,
        "action_id": action_id,
        "program_id": program_id,
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "status": "completed",
        "correlation_id": action["correlation_id"],
        "campaign_id": action["campaign_id"],
        "created_at": now,
        "updated_at": now,
    }
    run = {
        "run_id": run_id,
        "job_id": job_id,
        "program_id": program_id,
        "node_id": "surface:endpoint:" + "f" * 64,
        "event_name": "crawl.completed",
        "execution_mode": "scheduled",
        "status": "completed",
        "attempt": 1,
        "target_count": 1,
        "terminal_outcome": "completed",
        "needs_reconcile": False,
        "retry_reason": None,
        "error": "token=should-redact",
        "created_at": now,
        "updated_at": now,
        "started_at": now,
        "finished_at": now,
    }
    outcome = _outcome(
        program_id=program_id,
        action_id=action_id,
        job_id=job_id,
        run_id=run_id,
        outcome_id=outcome_id,
        new_surface_nodes_count=4,
        new_surface_edges_count=2,
        new_surface_deltas_count=1,
    )
    feedback = {
        "feedback_id": feedback_id,
        "outcome_id": outcome_id,
        "program_id": program_id,
        "campaign_id": action["campaign_id"],
        "action_id": action_id,
        "job_id": job_id,
        "run_id": run_id,
        "manual_interest": True,
        "manual_stop": False,
        "continued_by_followup": None,
        "report_created": False,
        "triage_outcome": None,
        "actor": "human",
        "source": "workbench",
        "reason": "Authorization: Bearer should-redact",
        "confidence": 0.9,
        "created_at": now,
    }

    graph = build_action_lens_graph(
        program_id=program_id,
        actions=[action],
        targets=[target],
        policy_decisions=[policy],
        approval_requests=[approval_request],
        approval_decisions=[approval_decision],
        jobs=[job],
        runs=[run],
        outcomes=[outcome],
        feedback_events=[feedback],
        seed=None,
        depth=1,
        limit=100,
    )

    assert graph.lens.value == "action"
    assert graph.boundary["surface"] == "action_lens_lifecycle_read_model"
    assert graph.boundary["action_submission"] == "forbidden"
    assert {
        "action_lifecycle_overview",
        "allowed_action",
        "action_target",
        "policy_decision",
        "approval_request",
        "approval_decision",
        "action_job",
        "action_run",
        "action_outcome",
        "action_delta",
        "outcome_feedback",
    }.issubset({node.node_type for node in graph.nodes})
    assert {edge.relationship_type for edge in graph.edges}.issuperset({"HAS_POLICY_DECISION", "ENQUEUED_JOB", "PRODUCED_OUTCOME", "HAS_FEEDBACK"})
    assert all(edge.source_projection == "action_lifecycle" for edge in graph.edges)
    target_node = next(node for node in graph.nodes if node.node_type == "action_target")
    policy_node = next(node for node in graph.nodes if node.node_type == "policy_decision")
    feedback_node = next(node for node in graph.nodes if node.node_type == "outcome_feedback")
    assert "should-redact" not in str(target_node.properties)
    assert "should-redact" not in str(policy_node.metadata)
    assert "should-redact" not in str(feedback_node.metadata)
    assert graph.nodes[0].metadata["lifecycle_contract"]["execution_surface"] is False

    profile = action_entity_profile_from_graph(program_id=program_id, entity_key=f"action:{action_id}", graph=graph)
    memory = action_entity_memory_from_graph(program_id=program_id, entity_key=f"action:{action_id}", graph=graph)
    actions = action_entity_actions(program_id=program_id, entity_key=f"action:{action_id}")

    assert profile is not None
    assert memory is not None
    assert profile.boundary["surface"] == "action_entity_profile"
    assert memory.summaries[0]["execution_surface"] is False
    assert actions.actions == []
    assert actions.boundary["surface"] == "action_lens_read_only_no_action_affordances"


def test_workbench_hypothesis_lens_builds_reasoning_graph_without_finding_promotion() -> None:
    from api.infrastructure.workbench_hypothesis import (
        build_hypothesis_lens_graph,
        hypothesis_entity_actions,
        hypothesis_entity_memory_from_graph,
        hypothesis_entity_profile_from_graph,
    )

    program_id = uuid4()
    hypothesis_id = uuid4()
    signal_id = uuid4()
    evidence_id = uuid4()
    event_id = uuid4()
    score_id = uuid4()
    proposal_id = uuid4()
    now = datetime(2026, 6, 30, tzinfo=timezone.utc)
    fingerprint = "s" * 64
    hypothesis = {
        "hypothesis_id": hypothesis_id,
        "program_id": program_id,
        "hypothesis_type": "graph_surface_followup",
        "hypothesis_fingerprint": "h" * 64,
        "status": "needs_verification",
        "state_version": 2,
        "priority_score": 73,
        "confidence": 0.72,
        "severity_guess": "medium",
        "safety_level": "passive",
        "score_version": "hypothesis-builder-v1",
        "inputs_hash": "i" * 64,
        "source_signal_fingerprints": [fingerprint],
        "duplicate_of_hypothesis_id": None,
        "first_seen": now,
        "last_seen": now,
        "updated_at": now,
    }
    signal = {
        "signal_id": signal_id,
        "program_id": program_id,
        "producer_run_id": uuid4(),
        "signal_type": "surface_bridge_pressure",
        "signal_version": "structural-signal-v1",
        "rule_id": "bridge-pressure",
        "rule_version": "v1",
        "asset_type": "endpoint",
        "asset_id": "surface:endpoint:" + "a" * 64,
        "observation_id": None,
        "evidence_fingerprint": fingerprint,
        "confidence": 0.81,
        "payload_json": {"token": "should-redact", "component_id": 7},
        "created_at": now,
    }
    evidence = {
        "evidence_id": evidence_id,
        "hypothesis_id": hypothesis_id,
        "ref_type": "http_observation",
        "ref_id": "obs-1",
        "field_path": "headers.authorization",
        "role": "primary",
        "claim_type": "surface_signal",
        "claim": "Authorization: Bearer should-redact supports followup",
        "evidence_fingerprint": "e" * 64,
        "safe_excerpt": "Authorization: Bearer should-redact",
        "safe_excerpt_truncated": False,
        "evidence_source": "sanitizer",
        "sanitizer_version": "research-sanitizer-v1",
        "redaction_policy_version": "redaction-policy-v1",
        "sensitivity_level": "credential_like",
        "redaction_rules_triggered": ["sensitive_header"],
        "safe_for_search": True,
        "safe_for_llm": True,
        "created_at": now,
    }
    event = {
        "event_id": event_id,
        "hypothesis_id": hypothesis_id,
        "event_type": "critic_reviewed",
        "aggregate_version": 2,
        "actor": "critic",
        "reason": "token=should-redact but needs verification",
        "payload_json": {"decision": "needs_verification", "api_key": "should-redact"},
        "created_at": now,
    }
    score = {
        "score_id": score_id,
        "hypothesis_id": hypothesis_id,
        "score_version": "hypothesis-builder-v1",
        "priority_score": 73,
        "confidence": 0.72,
        "severity_guess": "medium",
        "safety_level": "passive",
        "inputs_hash": "i" * 64,
        "factors_json": {"password": "should-redact", "evidence_count": 1},
        "created_at": now,
    }
    proposal = {
        "proposal_id": proposal_id,
        "program_id": program_id,
        "campaign_id": uuid4(),
        "task_id": uuid4(),
        "source_message_id": uuid4(),
        "agent_key": "critic-agent",
        "proposal_key": "proposal-1",
        "proposal_type": "tool_action",
        "status": "pending",
        "title": "Verify endpoint family",
        "summary": "Check related routes",
        "rationale": "hypothesis followup",
        "capability_id": "katana",
        "profile_id": "safe-crawl",
        "priority": "medium",
        "expected_gain": "More endpoint evidence",
        "action_intent": "crawl",
        "action_params": {"hypothesis_id": str(hypothesis_id), "access_token": "should-redact"},
        "context_refs": [{"type": "research_hypothesis", "id": str(hypothesis_id)}],
        "metadata": {"hypothesis_fingerprint": hypothesis["hypothesis_fingerprint"]},
        "accepted_action_id": None,
        "review_feedback": {},
        "created_at": now,
        "updated_at": now,
    }

    graph = build_hypothesis_lens_graph(
        program_id=program_id,
        hypotheses=[hypothesis],
        evidence_rows=[evidence],
        signal_rows=[signal],
        event_rows=[event],
        score_rows=[score],
        proposal_rows=[proposal],
        seed=None,
        depth=1,
        limit=100,
    )

    assert graph.lens.value == "hypothesis"
    assert graph.boundary["surface"] == "hypothesis_lens_reasoning_read_model"
    assert graph.boundary["proposal_creation"] == "forbidden"
    assert graph.boundary["action_submission"] == "forbidden"
    assert {
        "hypothesis_overview",
        "structural_signal",
        "research_hypothesis",
        "hypothesis_evidence",
        "hypothesis_critic_status",
        "hypothesis_score_history",
        "hypothesis_proposed_action",
    }.issubset({node.node_type for node in graph.nodes})
    assert {edge.relationship_type for edge in graph.edges}.issuperset(
        {"HAS_SIGNAL", "SUPPORTS_HYPOTHESIS", "EVIDENCE_FOR", "HAS_CRITIC_EVENT", "HAS_SCORE_HISTORY", "HAS_PROPOSED_ACTION"}
    )
    assert all(edge.source_projection == "hypothesis_read_model" for edge in graph.edges)
    assert graph.nodes[0].metadata["hypothesis_contract"]["hypothesis_is_finding"] is False
    assert graph.nodes[0].metadata["hypothesis_contract"]["execution_surface"] is False
    assert "should-redact" not in str([node.properties for node in graph.nodes])
    assert "should-redact" not in str([node.metadata for node in graph.nodes])

    profile = hypothesis_entity_profile_from_graph(program_id=program_id, entity_key=f"hypothesis:{hypothesis_id}", graph=graph)
    memory = hypothesis_entity_memory_from_graph(program_id=program_id, entity_key=f"hypothesis:{hypothesis_id}", graph=graph)
    actions = hypothesis_entity_actions(program_id=program_id, entity_key=f"hypothesis:{hypothesis_id}")

    assert profile is not None
    assert memory is not None
    assert profile.boundary["surface"] == "hypothesis_entity_profile"
    assert profile.profile["hypothesis_is_finding"] is False
    assert memory.summaries[0]["summary_is_truth"] is False
    assert memory.summaries[0]["not_semantics"] == "finding/proof/verdict/confirmed_vulnerability"
    assert actions.actions == []
    assert actions.boundary["surface"] == "hypothesis_lens_read_only_no_action_affordances"


def test_workbench_projection_control_falls_back_to_surface_snapshot_components_when_neo4j_is_unavailable() -> None:
    from api.infrastructure import workbench_projection_control

    source = workbench_projection_control.__loader__.get_source(workbench_projection_control.__name__)

    assert "_materialize_surface_components_from_surface_snapshot" in source
    assert "surface-local-route-family-components" in source
    assert "surface_snapshot_route_family_grouping" in source
    assert "Neo4j/GDS component analytics were unavailable" in source
    assert "gds_execution" in source
    assert "not_performed" in source
