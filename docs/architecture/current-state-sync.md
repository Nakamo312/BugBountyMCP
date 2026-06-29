# Current Architecture Sync

Status: current implementation snapshot

Date: 2026-06-27

## Purpose

This document records the current state after the action-outcome, Surface Map,
Neo4j/GDS, proposal, and graph-projector operational patches. It exists to stop
future work from rebuilding layers that already exist and to separate three
things that were previously mixed together:

1. ideas already present in the original schema and architecture documents;
2. layers that are now implemented in code;
3. layers that remain only planned or partial.

The project direction remains unchanged: do not build a handwritten rule engine,
closed vulnerability taxonomy, or LLM-centered scanner. The core loop is:

```text
state -> action -> changed representation -> memory -> feedback -> next choice
```

Quality must be measured by changed representation, changed choice, cost,
feedback, and structural graph properties. Do not reward raw volume as the main
signal.

## What Already Existed Before These Patches

The original repository already contained the major architectural skeleton:

- `Surface Map` schema in Alembic: `surface_snapshots`, `surface_nodes`,
  `surface_edges`, `surface_clusters`, `surface_cluster_members`,
  `surface_cluster_labels`, and `surface_deltas`.
- `action_outcomes` columns for `before_surface_snapshot_id`,
  `after_surface_snapshot_id`, and surface novelty counters.
- ADR documentation for Surface Map as a mathematical surface representation,
  not a manual business taxonomy.
- Action outcome memory, action experience proposals, and a Neo4j/GDS
  `nodeSimilarity` contour for `ActionOutcome <-> OutcomeFeature` experience.
- GraphFact projection infrastructure, durable projection queues, rebuild,
  safe query templates, and GDS readiness checks.

That means the implemented work below should be read as activation and wiring of
an existing direction, not as a new architecture.

## What Is Implemented Now

### 0. Credential Reference And Secret Storage Boundary

Authenticated testing is modeled through opaque `credential_ref` values and
`auth_injection` metadata. Raw tokens, cookies, API keys, session material,
Authorization headers, and password-like values must not appear in proposals,
action options, agent memory, runner logs, OpenSearch, Neo4j, or LangGraph state.

The storage foundation now consists of `credential_refs`,
`credential_secret_versions`, and `credential_leases`. The first table stores
non-secret identity metadata; the second stores encrypted/local secret pointers
such as ciphertext or external-vault references; the third stores short-lived
lease metadata for approved executions. `credential_refs.current_secret_version_id`
and refresh fields make the identity stable while secret versions rotate. This
enables future IDOR/authz tests to compare identities such as `user_a`, `user_b`,
`admin`, and `expired_user` without exposing the underlying secrets to the agent
or read models.

Secret refresh/rotation is explicit: replacing a token or session creates a new
secret version, retires the old current version, updates refresh metadata, and
keeps future leases bound to the new active version. Runner injection is
intentionally still separate: a lease is permission to materialize a secret, not
the secret itself.

### 1. Action Outcome Memory And Experience Utility

Completed runs are recorded as `action_outcomes`. The outcome record stores the
execution lineage, capability/profile, raw telemetry, cost/error signals,
feedback, and score breakdown.

The score path has been corrected so raw counters such as `new_hosts_count`,
`new_services_count`, `new_endpoints_count`, `new_graph_facts_count`, and
`new_search_documents_count` are not treated as qualitative novelty. They remain
telemetry/debug material only.

The current utility target is now experience-oriented:

```text
raw action telemetry
  + proposal decision shift
  -> experience utility
  -> updated action_outcomes.information_gain_score
  -> graph projection refresh
  -> future GDS ranking
```

The name `information_gain_score` is historical and now somewhat misleading. In
current behavior it acts as the utility value consumed by experience ranking.
If a future migration is acceptable, prefer a dedicated name such as
`experience_utility_score` while retaining backward compatibility.

### 2. Proposal Decision Shift

After proposals are materialized for a completed outcome, the proposal store now
records a decision-distribution trace in `action_experience_proposal_runs`.

The trace measures whether the completed action changed the next-action choice
field:

- entropy;
- entropy delta;
- focus gain;
- top-k overlap;
- total variation distance;
- rank movement;
- decision shift score.

This is the current implementation of qualitative delta at the choice layer. A
action is better when it changes the system's ability to choose the next action,
not merely when it emits many rows.

### 3. Surface Engine Runtime Graph Inputs

`surface-engine build-snapshot` now writes:

```text
surface_snapshots
surface_nodes
surface_edges
surface_deltas
```

The new runtime files are:

```text
services/surface-engine/surface_engine/edges.py
services/surface-engine/surface_engine/deltas.py
```

Edges are structural and shape-based. They link snapshot-local surface nodes via
mechanical forms such as route shape and response shape. They do not label nodes
as `admin`, `api`, `auth`, `docs`, or any vulnerability/business class.

Deltas compare the current snapshot with the previous snapshot and record
structural changes such as introduced nodes and edges. Novelty values are used as
inputs for later graph aggregation; raw counts are not the quality score.

### 4. Surface Map Graph Projection

Neo4j now receives Surface Map facts:

```text
SurfaceSnapshot
SurfaceNode
SurfaceDelta
SurfaceFingerprint
```

and relationships such as:

```text
HAS_SURFACE_NODE
SURFACE_EDGE
HAS_SURFACE_DELTA
HAS_SURFACE_FINGERPRINT
HAS_SURFACE_FINGERPRINT_FEATURE
```

`SurfaceNode` is snapshot-local. `SurfaceFingerprint` is the stable cross-snapshot
anchor used to compare current component probes with historical action outcomes.

`ActionOutcome` projection also includes mutable links:

```text
BEFORE_SURFACE_SNAPSHOT
AFTER_SURFACE_SNAPSHOT
```

### 5. Surface Graph Math In Neo4j/GDS

There are now two graph-math contours.

The original experience contour:

```text
ActionOutcome <-> OutcomeFeature
  -> gds.nodeSimilarity.stream
  -> learned capability/profile ranking
```

The new Surface Map contour:

```text
SurfaceNode --SURFACE_EDGE-- SurfaceNode
  -> GDS algorithms over a snapshot-local shape graph
```

Implemented methods live in:

```text
services/graph-projector/graph_projector/surface_gds.py
```

Current surface graph methods:

```text
connected_components()
  gds.wcc.stream
  returns connected surface regions for one snapshot

component_profiles()
  gds.wcc.stream + gds.degree.stream
  returns structural pressure by component

component_drift()
  WCC(previous snapshot) + WCC(current snapshot)
  compares components by stable node fingerprints

component_bridges()
  gds.wcc.stream + gds.degree.stream + gds.betweenness.stream
  estimates connector/bridge pressure by component

component_outliers()
  gds.wcc.stream + gds.nodeSimilarity.stream
  estimates structurally unusual components

component_coverage()
  WCC + ActionOutcome snapshot links
  estimates whether changed components already have action experience

component_action_candidates()
  changed component probe + SurfaceFingerprint similarity to historical outcomes
  returns advisory capability/profile candidates
```

These methods do not use endpoint word lists or hand-authored semantic enums.
They calculate graph structure: connected components, degree, betweenness,
similarity, drift, coverage, and experience-neighbor utility.

### 6. Component Candidates And Proposal Materialization

Surface component candidates no longer live only as transient GDS output. The
proposal worker appends them to the same internal proposal stream used by normal
action experience proposals:

```text
action_experience_proposal_runs
action_experience_proposals
```

The source is recorded as:

```text
neo4j-gds-surface-component-nodeSimilarity
```

These proposals are advisory only. They never create or execute actions by
themselves. The control boundary remains:

```text
proposal -> ActionService -> policy -> scope -> approval -> budget -> run
```

### 7. Proposal Feedback Loop

Operator review is stored on proposals, not on the source action outcome.

Supported review statuses:

```text
accepted
rejected
suppressed
```

This is intentional. Rejecting a proposed next action does not mean the action
that produced the source snapshot was bad. Proposal feedback affects future
proposal ranking through review priors, while the original action outcome remains
its own experience record.

Review priors are applied by `capability_id/profile_id` and proposal source.
`accepted` increases future similar proposals. `rejected` lowers them.
`suppressed` lowers them more strongly.

### 8. Mutable ActionOutcome Projection Refresh

`ActionOutcome` is now a mutable graph source. Its utility, feature buckets, and
snapshot links can change after proposal decision shift is recorded.

The Neo4j writer therefore replaces derived outgoing `ActionOutcome` edges before
re-projecting that node:

```text
HAS_OUTCOME_FEATURE
BEFORE_SURFACE_SNAPSHOT
AFTER_SURFACE_SNAPSHOT
```

This prevents a single outcome from retaining stale feature buckets or stale
snapshot links after refresh.

Other graph facts remain append/upsert style. Do not apply this replacement rule
to canonical inventory, raw artifacts, HTTP observations, JS references, or
surface nodes unless they become explicitly mutable projection nodes.

### 9. Selective Rebuild And Projector Operations

The graph projector now supports selective rebuild sources:

```bash
python -m graph_projector rebuild --source action_outcomes
python -m graph_projector rebuild --source surface_map
python -m graph_projector rebuild --source action_outcomes --source surface_map
```

Available source keys:

```text
raw_artifacts
canonical_inventory
http_observations
javascript_references
action_outcomes
surface_map
```

Operational read/repair commands now exist:

```bash
python -m graph_projector status
python -m graph_projector retry
python -m graph_projector health
python -m graph_projector diagnostics
python -m graph_projector process-surface-analysis-events
```

These commands read, repair, or process durable PostgreSQL queues:

```text
graph_projection_events
graph_fact_batches
surface_component_analysis_events
```

`surface_component_analysis_events` is a separate durable queue for downstream
Surface Component analysis materialization. It starts after `surface_map` graph
facts are applied to Neo4j; it is not a replacement for graph projection events.

### 10. Persisted Surface Component Analysis Read Model

Surface component analytics can now be materialized into PostgreSQL after a
GDS run. This is a read model, not a new scoring system and not a proposal/action
executor. Materialization can be requested manually or through a durable queue
that is enqueued after `surface_map` GraphFact batches are applied.

Tables:

```text
surface_component_analysis_events
surface_component_analysis_runs
surface_component_analysis_items
```

Commands:

```bash
python -m graph_projector surface-components-materialize \
  --program-id <uuid> \
  --snapshot-id <snapshot_id>

python -m graph_projector surface-components-materialized \
  --program-id <uuid> \
  --snapshot-id <snapshot_id>

python -m graph_projector process-surface-analysis-events
python -m graph_projector process-surface-analysis-events-loop
```

`surface-components-materialize` runs the existing `SurfaceComponentReportReader`
once, persists a versioned component analysis run, and stores per-component
metrics plus compact action candidate payloads. `surface-components-materialized`
reads the latest persisted result without re-running Neo4j/GDS.

This layer exists so UI, CLI, and ops consumers can inspect surface component
pressure/drift/bridge/outlier/coverage summaries without turning every read into
a GDS job.

The API read boundary is also available:

```http
GET /api/v1/surface-component-analysis?program_id=<uuid>&snapshot_id=<uuid>
GET /api/v1/surface-component-analysis/latest?program_id=<uuid>
```

Both endpoints read only `surface_component_analysis_runs` and
`surface_component_analysis_items`; they do not run Neo4j/GDS, materialize new
reports, create proposals, submit actions, or execute tools. `latest` is the UI
entrypoint when the operator has not copied a concrete snapshot id.

The dashboard exposes this persisted read model at:

```text
/surface-components
```

The page renders component pressure, drift, bridge, outlier, coverage,
exploration priority, and advisory action candidates from the materialized API.
It does not trigger GDS or materialization.


### 11. OpenSearch Surface Component Projection

The search indexer now exposes rebuildable OpenSearch targets for persisted
Surface Component analysis and Surface Map deltas:

```bash
python -m search_indexer reindex --target surface-components --program-id <uuid>
python -m search_indexer reindex --target surface-components --program-id <uuid> --analysis-run-id <analysis_run_uuid>
python -m search_indexer reindex --target surface-components --program-id <uuid> --snapshot-id <snapshot_uuid>
python -m search_indexer reindex --target surface-deltas --program-id <uuid>
python -m search_indexer reindex --target surface-deltas --program-id <uuid> --snapshot-id <snapshot_uuid>
```

Indexes:

```text
bb-surface-components
bb-surface-deltas
```

`surface-components` reads only the materialized PostgreSQL read model
`surface_component_analysis_runs` / `surface_component_analysis_items`. It does
not run Neo4j/GDS, create proposals, or execute actions. `surface-deltas` reads
only `surface_deltas`. Both builders use bounded JSON sanitization and static
mappings. The surface targets support incremental filters: `--analysis-run-id`
for a single materialized component-analysis run and `--snapshot-id` for one
component snapshot or delta `to_snapshot_id`.

A downstream durable queue now connects successful Surface Component analysis
materialization to incremental OpenSearch indexing:

```text
surface_component_analysis_events -> search_projection_events -> search_indexer process-events
```

When `process-surface-analysis-events` materializes a report, graph-projector
enqueues two OpenSearch events: one for `surface-components` scoped by
`analysis_run_id`, and one for `surface-deltas` scoped by `snapshot_id`.
Search-indexer processes those events through the same `reindex_target` path and
therefore reuses mapping, sanitization, and projection watermark logic. The
search projection queue has read-only and repair commands:

```bash
python -m search_indexer status
python -m search_indexer retry
python -m search_indexer health --json
python -m search_indexer diagnostics --json
```

These commands only inspect or reset the durable PostgreSQL queue; they do not
run Neo4j/GDS, materialize component analysis, or execute actions.


### 16. Program Projection Overview

A read-only API now provides one program-level snapshot of the projection pipeline:

```http
GET /api/v1/program-projection-overview?program_id=<uuid>
```

The overview joins durable PostgreSQL state only:

- latest `surface_snapshots`;
- latest `surface_component_analysis_runs/items`;
- `graph_projection_events`;
- `graph_fact_batches`;
- `surface_component_analysis_events`;
- `search_projection_events`;
- `action_experience_proposals`.

It reports whether Surface Component analysis is fresh relative to the latest
snapshot, whether the matching surface component / delta search projection has
processed, whether UI data is fresh, and which ops commands are likely relevant
next.

Boundary: this endpoint does not run Neo4j/GDS, rebuild, retry, materialize,
reindex OpenSearch, create proposals, submit actions, or execute tools.

Dashboard consumption: the main Dashboard page renders a read-only Projection Pipeline card backed by this endpoint. It shows freshness flags, queue backlog/error counts, pending experience proposals, suggested operator commands, the ordered operator plan, and CLI audit inspection commands for the local `projection run-step` JSONL trail. The browser does not read the local audit file and never executes those commands.


### 17. Command And Credential Reference Boundary

Runner execution now uses `CommandInvocation` as the infrastructure-level
process boundary. It carries only:

```text
argv
stdin
timeout
env overlay
credential_refs
```

`env overlay` is merged with the inherited process environment by
`CommandExecutor`; it is not logged with values and it does not replace the full
process environment. This lets future runner materialization use env-based
secrets without breaking PATH/tool lookup or leaking env values.

`credential_refs` are opaque identifiers reserved for the next credential lease
epic. They are not secrets and they do not resolve credentials yet. Their purpose
is to keep future authenticated execution out of agent context, proposal
payloads, raw command arguments, stdin payloads, logs, read models, and graph
projections.

Current rule: if a future action needs cookies, Authorization headers, bearer
tokens, API keys, or session material, agents and proposals may only carry an
opaque reference plus typed `auth_injection` metadata. Supported injection
metadata covers headers, cookies, cookie jars, environment variables, config
files, browser contexts, mTLS/proxy auth, and explicit CLI flags for tools that
have no safer interface. CLI flag materialization requires capability-profile
opt-in through bounded `allowed_cli_flags` and `allow_argv_exposure=true`. The
actual token material must be materialized later by an approved runner-side
lease/injection boundary after ActionService policy, scope, approval, and budget
checks pass.

Runner logs now report command shape through redaction helpers and stdin shape
through bounded summaries. Raw credential material must not appear in argv,
stdin, `ProcessEvent` payloads, parser payloads, artifacts, OpenSearch
documents, Neo4j facts, LangGraph state, or dashboard/API read models.

## What Is Not Implemented Yet

The following remain planned or partial:

- `surface_clusters`, `surface_cluster_members`, and `surface_cluster_labels`
  runtime population.
- OpenSearch projections for Surface Map clusters/cluster labels. Component analysis and deltas are already indexed through `surface-components` and `surface-deltas` search-indexer targets and have a durable incremental event queue.
- LLM cluster labels over compact evidence packs.
- Full coverage feedback from accepted component proposal to later executed
  action lineage. Proposal accept/reject/suppress exists, but deeper lineage
  analytics from accepted proposal to executed action remain partial.
- Metamorphic relations and principal-diff graph layers.
- Embeddings, KNN, Louvain/Leiden, conductance, spectral methods, link
  prediction, and temporal co-change beyond the current drift calculation.
- Renaming or splitting `information_gain_score` into a dedicated utility field.

## Do Not Rebuild These Layers

Avoid reimplementing these unless there is a precise bug:

- action outcome memory;
- action experience proposal storage;
- GDS `ActionOutcome <-> OutcomeFeature` ranking;
- surface snapshot/node/edge/delta writing;
- Surface Map Neo4j projection;
- surface WCC/profile/drift/bridge/outlier/coverage/candidate readers;
- component proposal materialization;
- proposal review guard and review priors;
- decision shift recording;
- mutable ActionOutcome projection refresh;
- selective graph rebuild;
- projector status/retry/health/diagnostics commands;
- surface component analysis event queue and worker;
- search projection event queue and worker;
- search-indexer status/retry/health/diagnostics around `search_projection_events`;
- program projection overview endpoint for end-to-end read-only freshness diagnostics.
- program projection operator plan endpoint for ordered read-only ops guidance.
- dashboard Projection Pipeline card that consumes the overview endpoint;
- dashboard read-only Operator Plan display derived from `/program-projection-overview/plan`.

Future changes should extend these layers instead of creating parallel stores,
parallel proposal tables, or a second action planner.

## Current Safe Next Steps

Prefer one of these next steps:

1. Add Surface Map OpenSearch projections for clusters and cluster labels once runtime clustering exists.
2. Add tests and docs around the mutable `information_gain_score` / experience
   utility naming issue before doing a migration.
3. Add dashboard/CLI visibility for search projection watermarks if operators need index-level freshness beyond queue state.

Do not add new semantic enums such as `AUTH_BOUNDARY`, `API_SURFACE`, or
`ADMIN_PANEL` as scoring primitives. Labels may exist later for explanation, but
not as the core utility function.


### bb projection overview

The `bb` CLI can now consume the read-only program projection overview without contacting Postgres, Neo4j, GDS, OpenSearch, or workers directly:

```bash
python -m bb_cli --program-id <uuid> projection overview
python -m bb_cli --program-id <uuid> projection plan
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --execute --yes
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --audit-log ./ops-audit.jsonl
python -m bb_cli --program-id <uuid> projection run-step process-search-projection-events --no-audit
python -m bb_cli --program-id <uuid> projection audit
python -m bb_cli --program-id <uuid> projection audit --step-id process-search-projection-events
python -m bb_cli --program-id <uuid> projection audit-summary
python -m bb_cli --program-id <uuid> projection audit-summary --step-id process-search-projection-events
python -m bb_cli --program-id <uuid> projection overview --json
```

It renders latest Surface Map snapshot state, latest persisted component analysis, graph/search durable queue counts, pending action-experience proposal counts, freshness flags, suggested operator commands, and local CLI audit inspection commands for projection run-step history. `projection plan` orders those commands into a read-only operator sequence. `projection run-step <step_id>` can preview or execute exactly one selected plan step through a fixed allow-list of canonical module commands (`python -m graph_projector`, `python -m search_indexer`, and read-only `python -m bb_cli` inspection commands); execution requires `--execute --yes` and uses `subprocess.run(..., shell=False)`. Preview and execute invocations append a bounded local JSONL audit event to `.bb/audit/projection-run-step.jsonl` unless `--no-audit` is passed; `--audit-log` can redirect it. `projection audit` is the read-only local audit viewer for that JSONL trail; `projection audit-summary` aggregates the same trail by operator step. It never invents commands, never submits actions, and never bypasses ActionService/policy.

Credential lease service note: `CredentialLeaseService` is the application-level boundary for lease TTL policy, purpose/capability/target binding, argv-exposure policy, audit-safe views, and runner-only secret resolution.
Credential DB store status: `PostgresCredentialStore` persists credential refs, secret versions, and leases with SQLAlchemy Core and requires an explicit `SecretCodec`; production should provide encrypted/vault-backed encoding, while tests/dev may explicitly use `DevOnlyPlaintextSecretCodec`.


Credential materialization status: `CredentialMaterializationPlan` exists as a runner-side, secret-bearing contract with audit/redacted views. `CommandExecutor` can now receive a validated env overlay through `CommandInvocation` and logs only env variable names. Concrete runner lease injection is still a future patch.


Credential secret storage now has a local encrypted Postgres codec and composition boundary: `build_credential_secret_codec(...)` / `build_postgres_credential_store(...)` choose the backend from `CREDENTIAL_SECRET_BACKEND`, defaulting to encrypted Postgres and requiring `CREDENTIAL_MASTER_KEY`. `LocalEncryptedSecretCodec` uses AES-256-GCM and stores only ciphertext/nonce/key metadata in `credential_secret_versions`; `DevOnlyPlaintextSecretCodec` remains explicit dev/test-only and requires `CREDENTIAL_ALLOW_DEV_PLAINTEXT=true`.
