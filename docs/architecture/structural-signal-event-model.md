# Structural Signal Event Model

Status: contract-only shape inventory.

This document describes the durable event/read-model boundary for structural graph
signals. It does not create a database table, write events, run GDS, promote
findings, create action proposals, or execute tools.

Machine-checkable source:

```text
services/graph-projector/graph_projector/structural_signal_contract.py
```

The module validates this shape at import time. A broken contract should fail
early instead of relying only on a separate test run.

## Role

A structural signal is a graph-derived observation over a typed projection
snapshot. It can support a hypothesis proposal, coverage planning, RAG/RLM task
selection, or human review.

Hard boundary:

```text
signal != finding
signal != action
signal != exploit recipe
signal != tool approval
```

A signal may say that structure is unusual, central, sparse, changed, similar, or
missing according to an allowed algorithm family. It must not claim impact or
vulnerability without evidence and explicit promotion.

## Durable event shape

The v1 event type is:

```text
structural_signal_generated
```

Required event fields:

```text
signal_id
signal_type
program_id
projection_name
projection_contract_version
projection_snapshot_id
algorithm_families
score
confidence
node_refs
edge_refs
evidence_refs
source_event_id
generated_by
generated_at
```

Reference fields are reference-only:

```text
node_refs
edge_refs
evidence_refs
source_event_id
projection_snapshot_id
```

These fields point to graph nodes, graph edges, source evidence, and projection
snapshot lineage. They do not embed raw HTTP payloads, raw parameter values,
secrets, cookies, Authorization headers, command argv, or artifacts.

## Projection signal contracts

The v1 structural signal event model currently covers signal shapes declared by:

```text
G_http v1
G_bipartite_endpoint_param v1
```

Each signal contract must match the projection inventory:

```text
signal_type
projection_name
projection_contract_version
source_event_type
algorithm_families
required_lineage_fields
evidence_ref_fields
forbidden_payload_fields
```

The `algorithm_families` for a signal must equal the mapping declared in
`ProjectionContract.output_signal_families`. This prevents a signal from using
an unrelated score family while keeping the same name. The signal `source_event_type`
must also match the ready snapshot event for its projection.

## Forbidden event fields

The structural signal event must not include fields that promote it into another
lifecycle:

```text
finding_id
finding_status
action_id
action_proposal_id
approval_request_id
command_invocation_id
command_argv
credential_secret_version_id
credential_lease_id
```

Signal consumers may create later hypothesis proposals, but that is a separate
reviewed transition. The signal event itself does not request execution.

## Forbidden payload fields

Signal references must not carry raw sensitive payloads:

```text
raw_headers
raw_request_body
raw_response_body
raw_body
body_preview
raw_url
full_url
url_sample
query
fragment
example_value
raw_value
secret_value
query_value
authorization
cookies
token
secret
password
api_key
session_cookie
```

## G_http event correction

`G_http` shape now describes output snapshots as:

```text
G_http_projection_snapshot_ready
```

A future request event should be modeled separately. Request events must not
contain nodes, edges, or structural signal contracts.

## Score semantics

The v1 shape reserves `score` and `confidence`, but it does not define runtime
payload validation. The persistence patch must define numeric ranges before any
structural signal is stored. The intended baseline is:

```text
confidence: 0.0..1.0
score: signal-specific normalized value, preferably 0.0..1.0 unless the signal contract says otherwise
```

This prevents incompatible score scales from leaking out of graph math.


## Hypothesis proposal boundary

The next contract-only transition is documented in:

```text
docs/architecture/hypothesis-from-structural-signal-contract.md
services/graph-projector/graph_projector/hypothesis_from_signal_contract.py
```

That layer covers only:

```text
StructuralSignal -> HypothesisProposal
```

It still does not create findings, action proposals, approval requests, command
invocations, or tool runs.

## Future implementation notes

A later persistence patch may add a `StructuralSignal` table or event-store
payload schema. That patch must preserve this boundary:

```text
StructuralSignal -> HypothesisProposal -> ActionProposal -> ActionService approval -> Tool run -> Outcome
```

It must store projection name and contract version with every signal so old
signals remain interpretable after projection contracts evolve.
