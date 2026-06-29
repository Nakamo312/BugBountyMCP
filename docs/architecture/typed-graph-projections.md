# Typed Graph Projections

Status: machine-checkable shape inventory, no runtime projection builders

Date: 2026-06-28

## Purpose

Typed graph projections prevent graph math from collapsing into one large,
untyped Neo4j surface. Each projection names its mathematical space, the facts it
can consume, the algorithms it may support later, and the structural signals it
may emit.

This document mirrors the machine-readable inventory in
`services/graph-projector/graph_projector/projection_contracts.py`. The Python
inventory is the contract source used by tests. The dedicated minimal `G_http`
projection event/shape contract lives in
`services/graph-projector/graph_projector/g_http_projection_contract.py` and is
reviewed in `docs/architecture/g-http-projection-contract.md`; the first bipartite shape is reviewed in `docs/architecture/bipartite-endpoint-param-contract.md`. This document is the human review
surface. It is a machine-checkable shape inventory: tests validate required fields,
contract versions, source projection dependencies, and bounded algorithm families,
but the prose semantics still require review.

## Contract shape

Every `ProjectionContract` must define:

```text
name
contract_version
purpose
source_projections
input_facts
node_types
edge_types
algorithm_families
allowed_algorithms
output_signals
output_signal_families
lineage_requirements
sensitivity_rules
forbidden_interpretations
failure_modes
status
```

`contract_version` starts at `v1` and must be referenced by future projection
snapshots and structural signals alongside the projection name. `source_projections`
records machine-checkable dependencies such as
`G_bipartite_endpoint_param -> G_http`. `algorithm_families` is a bounded enum
(`AlgorithmFamily`) while `allowed_algorithms` remains human-readable detail text.
`output_signal_families` maps each structural signal type to allowed bounded
algorithm families; it is still a contract, not a runtime signal class.

`status` must stay `contract_only` in this patch. A contract does not build a
Neo4j projection, create a GDS graph, emit a finding, or execute tools.

## Inventory

The required projection inventory is:

```text
G_asset
G_http
G_identity
G_finding
G_temporal
G_bipartite_endpoint_param
G_bipartite_host_tech
G_bipartite_endpoint_object
```

### G_asset

Purpose: rebuildable asset ownership, infrastructure grouping, service exposure,
and coverage reasoning.

Nodes include organization, domain, subdomain, host, ip, cidr, asn, service, and
technology. Edges include ownership, DNS/IP containment, service exposure, and
technology usage.

Allowed algorithms are limited to component, degree/centrality, same-backend
baseline, service co-location, and coverage summaries. Outputs are structural
signals such as asset component, service exposure, host/technology neighborhood,
and asset coverage gap signals.

Forbidden interpretation: service exposure, technology presence, or centrality is
not a vulnerability verdict and not permission to run a tool.

### G_http

Purpose: HTTP surface topology, endpoint neighborhoods, response-shape
similarity, coverage, and drift over observed routes.

Nodes include host, endpoint, route_template, method, param, body_schema,
response_shape, status_class, content_type, and observed_action. Edges represent
hosted endpoints, route templates, methods, params, body/response/status/content
shape, and observed action lineage.

Allowed algorithms include endpoint degree, endpoint similarity by parameter or
response-shape neighborhood, route-template component coverage, and coverage or
drift summary. Outputs are structural signals such as HTTP endpoint
neighborhood, coverage gap, drift, and missing relation candidate signals.

Forbidden interpretation: parameter names are not IDOR findings, admin-looking
routes are not admin vulnerability verdicts, JWT observations are not JWT-tamper
action engines, and missing CSRF-like observations are not findings.

### G_identity

Purpose: auth-context coverage and identity/object relationship reasoning without
exposing secrets.

Nodes include principal, role, tenant, auth_context, credential_ref, object_ref,
and observed_permission_boundary. Raw secrets, cookies, session material, and
Authorization headers are forbidden. Credential refs are opaque handles only.

Outputs are identity coverage gap, principal/object neighborhood, and auth
context comparison signals. Reachability and role similarity are not privilege
escalation verdicts.

### G_finding

Purpose: evidence lineage, hypothesis-to-evidence traceability, duplicate
candidate grouping, root-cause grouping, and report synthesis.

Nodes include structural_signal, hypothesis, evidence, finding, root_cause,
report_section, and action_outcome. Edges represent proposal lineage, evidence
support, promotion, grouping, report mention, and outcome observation.

Outputs are evidence coverage, duplicate finding candidate, root-cause grouping
candidate, and report traceability signals. A structural signal is not a finding;
a grouping candidate is not a final report decision.

### G_temporal

Purpose: temporal drift, co-change, novelty decay, replay, and before/after
explanation.

Nodes include snapshot, appeared, disappeared, changed, stable_fingerprint,
action_window, and observation_time. Edges express snapshot order, delta classes,
stable identity, action windows, and observation time.

Outputs are temporal drift, co-change cluster, novelty decay, and replay window
signals. Co-change is not causality; drift is not a bug verdict; novelty is not
severity.

### G_bipartite_endpoint_param

Purpose: endpoint-parameter neighborhoods for missing relation suggestions and
endpoint similarity.

This projection uses endpoint and param nodes with `HAS_PARAM` edges. It supports
endpoint degree, parameter centrality, common parameter neighborhoods, Jaccard
overlap similarity, and a simple bipartite link prediction baseline.

Outputs are endpoint/parameter similarity, parameter centrality, and missing
endpoint-param candidate signals. Predicted edges remain advisory; they do not
become canonical facts.

### G_bipartite_host_tech

Purpose: host-technology neighborhoods for clustering, same-backend hints, and
coverage by technology family.

This projection uses host and technology nodes with `USES_TECHNOLOGY` edges. It
supports host similarity, technology centrality, common technology neighborhoods,
and coverage by technology family.

Outputs are host/technology similarity, technology coverage, and same-backend
candidate signals. Same technology is not ownership proof and not an exploit
path.

### G_bipartite_endpoint_object

Purpose: endpoint-object relationship discovery, missing observation suggestions,
and object coverage.

Nodes include endpoint, object_type, object_ref, and entity_shape. Edges describe
handled object types, referenced objects, and returned entity shapes.

Outputs are endpoint/object coverage, missing endpoint-object candidate, and
entity shape neighborhood signals. Object relationships are not authorization
proof and missing candidates are not findings.

## Acceptance rule

Future graph work must reference one `ProjectionContract` by name and state which
input facts it consumes, which allowed algorithm family it uses, which structural
signal it emits, and which lineage fields connect the signal back to canonical
PostgreSQL memory.

A patch that adds GDS/Cypher logic without a projection contract name and
`contract_version` should be rejected. A patch that adds an algorithm outside
the contract's `AlgorithmFamily` values should also be rejected.


## Dedicated bipartite endpoint-param contract

`G_bipartite_endpoint_param` now has a dedicated shape contract in `services/graph-projector/graph_projector/g_bipartite_endpoint_param_contract.py` and a review document in `docs/architecture/bipartite-endpoint-param-contract.md`. It depends on `G_http v1`, emits only structural signal type contracts, and forbids raw parameter values or raw URL samples.

## Structural signal boundary

Structural signal events are modeled in `structural-signal-event-model.md`. Projection contracts emit structural signal shapes only; signal events remain separate from findings and actions.
