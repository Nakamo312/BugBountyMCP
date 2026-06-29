"""Bounded-context SQLAlchemy table declarations."""

from .base import metadata

from .core import (
    programs,
    scope_rules,
    root_inputs,
)

from .credentials import (
    credential_refs,
    credential_secret_versions,
    credential_leases,
)

from .inventory import (
    hosts,
    ip_addresses,
    host_ips,
    services,
    endpoints,
    input_parameters,
    headers,
    raw_body,
    dns_records,
    organizations,
    asns,
    cidrs,
)

from .scanner import (
    vuln_types,
    scanner_templates,
    scanner_executions,
    payloads,
)

from .tool_catalog import (
    tool_catalog_snapshots,
    tool_catalog_entries,
)

from .orchestration import (
    campaigns,
    action_requests,
    action_request_targets,
    action_request_options,
    scope_decisions,
    approval_requests,
    approval_decisions,
    policy_decisions,
    agent_tasks,
    agent_runtime_usage_daily,
    agent_task_messages,
    agent_action_proposals,
    agent_action_proposal_feedback_events,
    agent_workflows,
    agent_workflow_runs,
    agent_subscriptions,
    agent_inbox,
    agent_wait_conditions,
    agent_result_sets,
)

from .action_execution import (
    jobs,
    runs,
    action_outcomes,
    action_outcome_feedback_events,
    action_experience_proposal_runs,
    action_experience_proposals,
    raw_artifacts,
)

from .dispatch_outbox import (
    event_store,
    event_dispatches,
)

from .graph_projection import (
    cypher_query_audits,
    graph_fact_batches,
    graph_projection_events,
    projection_watermarks,
)

from .surface_map import (
    surface_snapshots,
    surface_nodes,
    surface_edges,
    surface_clusters,
    surface_cluster_members,
    surface_cluster_labels,
    surface_deltas,
    surface_component_analysis_runs,
    surface_component_analysis_items,
    surface_component_analysis_events,
)

from .search_projection import (
    search_projection_events,
    http_observations,
    http_observation_headers,
    javascript_references,
)

from .research import (
    research_producer_runs,
    research_signals,
    research_hypotheses,
    research_hypothesis_evidence,
    research_hypothesis_events,
    research_hypothesis_score_history,
    research_suppression_rules,
)

from .results import (
    findings,
    leaks,
)

__all__ = [
    "metadata",
    "programs",
    "scope_rules",
    "root_inputs",
    "credential_refs",
    "credential_secret_versions",
    "credential_leases",
    "hosts",
    "ip_addresses",
    "host_ips",
    "services",
    "endpoints",
    "input_parameters",
    "headers",
    "raw_body",
    "dns_records",
    "organizations",
    "asns",
    "cidrs",
    "vuln_types",
    "scanner_templates",
    "scanner_executions",
    "payloads",
    "tool_catalog_snapshots",
    "tool_catalog_entries",
    "campaigns",
    "action_requests",
    "action_request_targets",
    "action_request_options",
    "scope_decisions",
    "approval_requests",
    "approval_decisions",
    "policy_decisions",
    "agent_tasks",
    "agent_runtime_usage_daily",
    "agent_task_messages",
    "agent_action_proposals",
    "agent_action_proposal_feedback_events",
    "agent_workflows",
    "agent_workflow_runs",
    "agent_subscriptions",
    "agent_inbox",
    "agent_wait_conditions",
    "agent_result_sets",
    "jobs",
    "runs",
    "action_outcomes",
    "action_outcome_feedback_events",
    "action_experience_proposal_runs",
    "action_experience_proposals",
    "raw_artifacts",
    "event_store",
    "event_dispatches",
    "cypher_query_audits",
    "graph_fact_batches",
    "graph_projection_events",
    "projection_watermarks",
    "surface_snapshots",
    "surface_nodes",
    "surface_edges",
    "surface_clusters",
    "surface_cluster_members",
    "surface_cluster_labels",
    "surface_deltas",
    "surface_component_analysis_runs",
    "surface_component_analysis_items",
    "surface_component_analysis_events",
    "search_projection_events",
    "http_observations",
    "http_observation_headers",
    "javascript_references",
    "research_producer_runs",
    "research_signals",
    "research_hypotheses",
    "research_hypothesis_evidence",
    "research_hypothesis_events",
    "research_hypothesis_score_history",
    "research_suppression_rules",
    "findings",
    "leaks",
]
