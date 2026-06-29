# G_bipartite_endpoint_param Baseline Contract

Status: shape and event contract only, no runtime projection builder, no GDS

Date: 2026-06-28

## Purpose

`G_bipartite_endpoint_param` is the first bipartite projection contract layered on
an existing typed projection. It narrows `G_http` to an endpoint ↔ parameter
neighborhood space for similarity, parameter centrality, and missing relation
candidate signals.

The machine-checked source is:

```text
services/graph-projector/graph_projector/g_bipartite_endpoint_param_contract.py
```

This contract does not create Neo4j nodes, run Cypher, run GDS, emit findings, or
execute actions. It only defines the event/shape boundary a later runtime
projection implementation must satisfy.

## Source projection dependency

The projection depends on the versioned `G_http` contract:

```text
source_projection = G_http v1
source_event_type = G_http_projection_snapshot_ready
projection_name = G_bipartite_endpoint_param
contract_version = v1
output_event_type = G_bipartite_endpoint_param_projection_snapshot_ready
```

A future projection snapshot or structural signal must preserve both its own
`projection_contract_version` and the source `G_http` contract version. This is
needed because endpoint/param identity semantics may change as `G_http` evolves.

The shape describes the ready projection snapshot output. A request event would
not carry nodes, edges, or structural signal contracts and must be modeled
separately.

## Nodes

The minimal bipartite nodes are:

```text
endpoint
param
```

The `endpoint` node is sourced from the `G_http` endpoint node surface. The
`param` node is sourced from the `G_http` param node surface. `param` identity is
based on normalized `location`, `name`, and `normalization_version`; raw
parameter values are not part of node identity or payload.

`param` identity is scoped to the projection snapshot. It must not be reused as a
global Neo4j identity without an explicit scope field. This prevents common names
such as `id`, `token`, or `page` from being merged across unrelated programs,
targets, or source snapshots.

Forbidden payload examples include:

```text
example_value
raw_value
secret_value
query_value
raw_url
url_sample
query
fragment
authorization
cookies
```

## Edge

The minimal bipartite edge is:

```text
endpoint -[HAS_PARAM]-> param
```

The edge represents an observed endpoint/parameter relation inherited from
`G_http`. It is not a predicted edge, not a canonical new fact, and not a tool
execution instruction.

Relation identifiers belong to the edge lineage, not the snapshot lineage:

```text
edge_lineage_fields:
  endpoint_id
  param_id
  source_projection_snapshot_id
```

## Structural signal mapping

The projection advertises three structural signal type contracts:

```text
EndpointParamSimilaritySignal -> JACCARD_SIMILARITY
ParamCentralitySignal -> DEGREE, CENTRALITY
MissingEndpointParamCandidateSignal -> BIPARTITE_LINK_PREDICTION_BASELINE
```

Signal evidence is shape-specific:

```text
EndpointParamSimilaritySignal:
  endpoint_ids
  shared_param_ids

ParamCentralitySignal:
  param_id
  endpoint_ids

MissingEndpointParamCandidateSignal:
  candidate_endpoint_id
  candidate_param_id
  neighbor_endpoint_ids
```

`MissingEndpointParamCandidateSignal` is advisory. It can propose a missing
observation or hypothesis seed, but it is not an IDOR finding, not a proof, and
not permission to run a CLI tool.

## Required lineage

The projection snapshot preserves only snapshot-level lineage:

```text
snapshot_lineage_fields:
  program_id
  projection_name
  projection_contract_version
  projection_snapshot_id
  source_projection_name
  source_projection_contract_version
  source_projection_snapshot_id
  normalization_version
```

A projection snapshot contains many endpoints and many params. Therefore it must
not require a single `endpoint_id` or `param_id`. Those identifiers belong to
edge lineage or signal evidence refs.

If a future implementation cannot preserve source projection lineage, it must not
emit the snapshot or signal.

## Guardrails

This projection is a structural signal space only:

```text
shared id-like params are not IDOR findings
missing endpoint-param candidates are not observed requests
param centrality is not an action instruction
similarity is not proof of authorization weakness
```

A future implementation patch must reference this contract and `contract_version`
before it adds Cypher/GDS for endpoint ↔ param analysis.
