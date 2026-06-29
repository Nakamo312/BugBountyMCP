# G_http Minimal Projection Contract

Status: shape and event contract only, no runtime projection builder, no GDS

Date: 2026-06-28

## Purpose

`G_http` is the first typed projection to receive a dedicated projection shape
contract after the projection inventory. This document explains the human review
surface; the machine-checked source is:

```text
services/graph-projector/graph_projector/g_http_projection_contract.py
```

The contract defines the minimal HTTP surface projection event shape. It does
not create Neo4j nodes, run Cypher, run GDS, emit findings, or execute actions.
It also does not prove that signal implementation classes exist. Names such as
`HttpCoverageGapSignal` are structural signal type contracts, not runtime signal
classes.

## Versioned source contract

The event shape must reference:

```text
projection_name = G_http
contract_version = v1
source_event_types = http_observations_ready
```

Future projection snapshots and structural signals must preserve both the
projection name and `contract_version`. A signal that only says `G_http` is not
specific enough once the projection evolves.

## Canonical source records and lineage surfaces

The minimal source records are canonical HTTP/inventory records only:

```text
HTTPObservationModel
HTTPObservationHeaderModel
EndpointModel
ServiceModel
HostModel
IPAddressModel
```

`Run`, `action_outcome`, and `raw_artifact` references are lineage surfaces, not
`G_http` source records. They preserve provenance and replay/audit links without
turning the HTTP projection contract into a catch-all action execution graph.

The matching source tables are:

```text
http_observations
http_observation_headers
endpoints
services
hosts
ip_addresses
```

The lineage tables are:

```text
runs
action_outcomes
raw_artifacts
```

This is still shape-level validation. It checks that the named record/table
surfaces exist, but it does not prove that every field has a populated value for
every observation.

## Nodes

The minimal `G_http` nodes are:

```text
endpoint
route_template
method
param
body_schema
response_shape
status_class
content_type
observed_action
```

Forbidden payload examples include raw request/response bodies, raw header
values, cookies, Authorization values, tokens, secrets, example parameter values,
raw parameter values, raw URLs, query values, fragments, and URL samples. `G_http`
v1 keeps route templates and identity fields, not raw URL examples.

Node identity fields must be explainable by required properties, required lineage
fields, or explicit identity-only fields. A key field may not silently depend on a
value that the event shape never emits or preserves.

## Edges

The minimal `G_http` edges are:

```text
HAS_ROUTE_TEMPLATE
USES_METHOD
HAS_PARAM
HAS_BODY_SCHEMA
RETURNS_RESPONSE_SHAPE
RETURNS_STATUS_CLASS
RETURNS_CONTENT_TYPE
OBSERVED_BY_ACTION
```

These edges encode observed HTTP surface structure. They are not vulnerability
proofs and they do not authorize tool execution.

## Structural signal mapping

`G_http` structural signal types are mapped to bounded algorithm families:

```text
HttpEndpointNeighborhoodSignal -> DEGREE, JACCARD_SIMILARITY
HttpCoverageGapSignal -> COVERAGE_SUMMARY
HttpDriftSignal -> DRIFT_SUMMARY
HttpMissingRelationCandidateSignal -> JACCARD_SIMILARITY, COVERAGE_SUMMARY
```

The mapping prevents a contract from advertising one signal and using an
unrelated algorithm family. It still does not validate a concrete runtime GDS
implementation.

## Required lineage

Each future `G_http` projection event/signal must preserve at least:

```text
program_id
projection_name
projection_contract_version
projection_snapshot_id
http_observation_id
endpoint_id
service_id
source_action_outcome_id
run_id
raw_artifact_id
normalization_version
```

Where a field is unavailable, the future implementation must record uncertainty
or omit the signal rather than manufacturing lineage.

## Guardrails

`G_http` signals are structural signals only:

```text
parameter names are not IDOR findings
admin-looking routes are not admin vulnerability verdicts
JWT observations are not JWT-tamper action engines
missing CSRF-like observations are not findings
```

A future implementation patch must be rejected if it adds Cypher/GDS without
referencing `G_http` and `contract_version`, emits findings directly, or routes a
signal into `ActionService` without the hypothesis/proposal/approval path.
