# Graph Algorithm Backlog

Status: inventory and ordering contract, no new runtime algorithms

Date: 2026-06-28

## Purpose

This document is the backlog gate for graph math after the research operating
model and graph math role baseline. It prevents Neo4j/GDS work from drifting
into ad-hoc Cypher, vulnerability recipes, or one large untyped property graph.

The backlog records what already exists, what mathematical spaces are missing,
and which algorithm families should come next. It does not implement an
algorithm, create a finding, run a tool, or change ActionService boundaries.

## Non-goals

Do not add new GDS calls from this backlog patch.

Do not encode attack recipes such as:

```text
param name contains id -> IDOR
admin path -> admin action
jwt observed -> JWT tamper run
missing csrf token -> finding
```

Those strings can appear later as post-hoc labels, hypothesis explanations, RAG
filters, or report facets. They are not graph action engines.

Do not treat Neo4j as canonical memory. PostgreSQL remains the source of truth;
Neo4j, GDS, and OpenSearch are rebuildable projections/read models.

## Existing implemented graph/projector pieces

The current branch already has graph infrastructure and two graph-math contours.
Do not rebuild these layers without a precise bug.

### Durable projection infrastructure

Implemented:

```text
GraphFact contracts
GraphFactBatchStore
GraphFactBatchApplicator
GraphFactWriter
ontology.yaml / GraphOntologyRegistry
safe query templates
selective rebuild service
retry/status/health/diagnostics
projection-event worker
raw artifact GraphFact producer
typed canonical producers for HTTP observations, JavaScript references, and action outcomes
canonical inventory rebuild path
GraphProjector CLI boundary with thin __main__.py
```

This layer projects PostgreSQL/canonical facts to Neo4j. It is not yet the typed
GDS contract layer.

### Action outcome experience contour

Implemented:

```text
ActionOutcome <-> OutcomeFeature
ActionOutcome mutable utility / feedback projection refresh
nodeSimilarity over outcome-feature neighborhoods
learned capability/profile ranking support
```

Purpose: reuse historical action experience when selecting future hypotheses or
capability/profile proposals.

Keep: advisory ranking only. It must not execute actions.

### Surface Map contour

Implemented:

```text
SurfaceSnapshot
SurfaceNode
SurfaceEdge / SURFACE_EDGE
SurfaceDelta
SurfaceFingerprint
SurfaceFingerprint feature anchors
ActionOutcome BEFORE_SURFACE_SNAPSHOT / AFTER_SURFACE_SNAPSHOT links
surface component analysis materialization
surface component analysis event queue
surface component OpenSearch projection
```

Implemented GDS readers:

```text
connected_components()           -> WCC over one snapshot
component_profiles()             -> WCC + degree
component_bridges()              -> WCC + degree + betweenness
component_outliers()             -> WCC + nodeSimilarity
component_coverage()             -> WCC + ActionOutcome snapshot links
component_drift()                -> WCC(previous) + WCC(current) by fingerprints
component_action_candidates()    -> changed component probe + SurfaceFingerprint similarity to historical outcomes
```

Purpose: component pressure, drift, bridge pressure, outlier pressure, coverage,
and advisory action-candidate context.

Keep: structural signals and proposals only. Signal is not finding.

## Missing typed projection contracts

The next graph work now has a machine-checkable contract source of truth:
`services/graph-projector/graph_projector/projection_contracts.py`. Each
`ProjectionContract` defines name, contract_version, purpose, source_projections,
input facts (the required facts), node types, edge types, bounded AlgorithmFamily values, human-readable
allowed algorithms, output structural signals, lineage requirements, sensitivity
rules, forbidden interpretations, and failure modes. The phrase allowed algorithms
is contract detail text, not permission to add code before the projection
implementation exists. Future projection snapshots and structural signals must
record projection name plus contract_version. `output_signal_families` maps each
structural signal type to bounded `AlgorithmFamily` values so prose-only
`allowed_algorithms` cannot drift unnoticed.

### G_asset

Mathematical space:

```text
organization / domain / subdomain / host / ip / cidr / asn / service / technology
```

Primary purpose:

```text
asset ownership, infrastructure grouping, service exposure shape, rebuildable inventory reasoning
```

Likely algorithms:

```text
connected components
centrality / degree distributions
same-backend candidate baselines
service co-location summaries
coverage over hosts/services
```

Dependencies:

```text
canonical host/IP/service/technology facts
inventory GraphFact producer coverage
projection contract tests
```

### G_http

Dedicated shape contract:

```text
services/graph-projector/graph_projector/g_http_projection_contract.py
docs/architecture/g-http-projection-contract.md
```

This contract is shape-level only. It validates event/node/edge/signal metadata,
source record names, lineage fields, and bounded signal algorithm families. It
does not prove runtime signal classes or database lineage columns.

Mathematical space:

```text
host / endpoint / route_template / method / param / body_schema / response_shape / status_class / content_type / observed_action
```

Primary purpose:

```text
HTTP surface topology, endpoint neighborhoods, response-shape similarity, coverage and drift over observed routes
```

Likely algorithms:

```text
endpoint degree
endpoint similarity by param/response/method neighborhoods
route-template component coverage
missing relation suggestions
coverage/drift scoring
```

Dependencies:

```text
canonical HTTP observations
endpoint/route-template normalization
response-shape extraction
projection event shape for HTTP surface facts
```

### G_identity

Mathematical space:

```text
principal / role / tenant / auth_context / credential_ref / object_ref / observed_permission_boundary
```

Primary purpose:

```text
auth-context coverage and identity/object relationship reasoning without exposing secrets
```

Likely algorithms:

```text
bipartite coverage summaries
role/tenant neighborhood comparison
principal-object reachability summaries
missing observation suggestions
```

Dependencies:

```text
credential refs without raw secrets
auth context observations
principal/object canonicalization
strict sensitivity rules
```

### G_finding

Mathematical space:

```text
structural_signal / hypothesis / evidence / finding / root_cause / report_section / action_outcome
```

Primary purpose:

```text
evidence lineage, duplicate/root-cause grouping, report synthesis, hypothesis-to-evidence traceability
```

Likely algorithms:

```text
similarity by evidence neighborhoods
root-cause candidate grouping
evidence coverage summaries
report graph traversal
```

Dependencies:

```text
StructuralSignal model
HypothesisProposal model
finding/evidence lineage contracts
```

### G_temporal

Mathematical space:

```text
snapshot / appeared / disappeared / changed / stable_fingerprint / action_window / observation_time
```

Primary purpose:

```text
temporal drift, co-change, novelty decay, replay and before/after explanation
```

Likely algorithms:

```text
component drift
co-change grouping
time-window coverage summaries
novelty decay ranking
```

Dependencies:

```text
snapshot lineage
stable fingerprints
surface deltas
historical action windows
```

### G_bipartite_endpoint_param

Mathematical space:

```text
endpoint <-> param
```

Primary purpose:

```text
missing relation suggestions and endpoint similarity from parameter neighborhoods
```

Likely algorithms:

```text
endpoint degree
param centrality
common param neighborhoods
Jaccard / overlap similarity
simple link prediction baseline
```

Dependencies:

```text
G_http endpoint and param nodes
canonical parameter normalization
```

### G_bipartite_host_tech

Mathematical space:

```text
host <-> technology
```

Primary purpose:

```text
host clustering by technology neighborhood and likely same-app/backend hints
```

Likely algorithms:

```text
host similarity
technology centrality
common technology neighborhoods
coverage by technology family
```

Dependencies:

```text
G_asset host/service facts
technology normalization
```

### G_bipartite_endpoint_object

Mathematical space:

```text
endpoint <-> object_type / object_ref / entity_shape
```

Primary purpose:

```text
endpoint-object relationship discovery, missing observation suggestions, and object coverage
```

Likely algorithms:

```text
endpoint-object degree
common object neighborhoods
endpoint likely handles entity baseline
object coverage summaries
```

Dependencies:

```text
G_http endpoints
object/entity extraction
identity/object lineage where available
```

## Missing algorithm families

These are backlog families, not immediate implementation requests.

### Link prediction baseline

Start with simple baselines before any GNN work:

```text
Jaccard
Common Neighbors
Adamic-Adar
Resource Allocation
bipartite neighborhood overlap
path/schema/behavior similarity ranker
```

Outputs are `PredictedRelationship` or `StructuralSignal`, not canonical facts
and not findings. A predicted edge can feed a hypothesis proposal or missing
observation request only.

### Component and community algorithms

Backlog:

```text
Louvain / Leiden only after typed projections and failure-mode notes
conductance and component quality summaries
component persistence across snapshots
component-level coverage decay
```

Do not add community labels before the projection contract states what a
community means in that projection.

### Spectral and embedding summaries

Backlog:

```text
spectral summaries for drift and anomaly baselines
feature snapshots for selected projections
KNN over embeddings only after evidence lineage and rebuild semantics exist
```

Do not use embeddings/KNN as an unexplained verdict layer.

### Temporal co-change

Backlog:

```text
snapshot-to-snapshot co-change grouping
appeared/disappeared/changed clusters
change propagation around action windows
novelty decay and stale-signal suppression
```

Dependencies: `G_temporal`, stable fingerprints, action windows, and evidence
lineage.

### Coverage and feedback loops

Backlog:

```text
proposal accepted -> action executed -> outcome observed -> component coverage updated
signal suppressed -> future ranking penalty
false-positive feedback -> historical utility update
```

Dependencies: StructuralSignal model, proposal review events, and action outcome
lineage.

## Implementation order

Do not implement more algorithms until the contracts exist. Recommended order:

```text
1. Typed projection contract inventory
2. G_http minimal projection contract
3. G_bipartite_endpoint_param baseline
4. StructuralSignal event/read model
5. Component coverage/drift scoring as deterministic metrics
6. HypothesisProposal from StructuralSignal contract
7. RAG/RLM task contracts over selected context
8. Link prediction baseline over bipartite projections
9. G_temporal temporal co-change
10. Community/spectral/embedding work only after lineage and typed contracts
```

## Acceptance rule for future graph work

A graph patch must state:

```text
projection_name
input facts
algorithm family
output structural signal
lineage fields
failure modes
why the output helps coverage, drift, replay, evidence selection, or hypothesis selection
```

If a patch mainly adds taxonomy, labels, or a dashboard decoration, postpone it.


## Dedicated endpoint-param bipartite contract

`G_bipartite_endpoint_param` has a contract-only shape in `services/graph-projector/graph_projector/g_bipartite_endpoint_param_contract.py` and a human review doc at `docs/architecture/bipartite-endpoint-param-contract.md`. It must remain a contract gate until a later runtime projection patch explicitly references `projection_name`, `contract_version`, and source `G_http v1` lineage.

## Structural signal event/read model

The contract-only event/read-model boundary is documented in `docs/architecture/structural-signal-event-model.md` and `docs/architecture/hypothesis-from-structural-signal-contract.md`. It is machine-checked in `structural_signal_contract.py` and `hypothesis_from_signal_contract.py`. Both contracts validate at import time. Runtime persistence remains a later patch and must define score/confidence numeric ranges before signals are stored.
