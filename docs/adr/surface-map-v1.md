# ADR: Surface Map V1

Status: proposed

Date: 2026-06-09

## Context

The project already has several distinct layers:

- raw collection and normalized observations: `hosts`, `services`, `endpoints`, `http_observations`, `http_observation_headers`, `raw_artifacts`;
- execution and safety: `action_requests`, `policy_decisions`, `scope_rules`, `jobs`, `runs`, `scanner_executions`, `event_store`;
- research candidates: `research_producer_runs`, `research_signals`, `research_hypotheses`, `research_hypothesis_evidence`, `research_hypothesis_events`, `research_hypothesis_score_history`, `research_suppression_rules`;
- rebuildable search projections: `search-indexer` and OpenSearch indices.

The next layer must not become a manual signature engine. Hardcoded service classes such as `crm`, `landing`, `admin`, `docs`, `ads`, or `infra` are not enough and will drift into a bad Nuclei-like model. The system must support unknown surface types, new business zones, repeated static families, route variants, temporal changes, and relationships between observations.

The intended direction is a mathematical surface map:

```text
observations
  -> canonical route/content/value fingerprints
  -> surface nodes and weighted edges
  -> surface clusters / communities
  -> optional LLM labels on clusters
  -> optional research hypotheses
  -> OpenSearch projections for search and UI
```

LLM usage must happen after the surface is compressed and structured. The LLM labels and explains clusters. It does not classify every raw endpoint independently and does not receive raw bodies or raw Burp traffic.

## Decision

Introduce a new bounded context called **Surface Map**.

The Surface Map is the source-of-truth representation for canonicalized attack-surface structure: nodes, edges, clusters, labels, snapshots, and deltas. PostgreSQL remains the source of truth. OpenSearch remains a rebuildable search projection.

The primary entities are deliberately generic:

- `surface_snapshots`
- `surface_nodes`
- `surface_edges`
- `surface_clusters`
- `surface_cluster_members`
- `surface_cluster_labels`
- `surface_deltas`

The model does not introduce a closed business taxonomy. Business labels are open vocabulary values proposed by algorithms, LLM, or humans.

Correct flow:

```text
PostgreSQL observations/raw metadata
  -> canonicalization / dedup worker
  -> surface_nodes / surface_edges
  -> clustering worker
  -> surface_clusters / surface_cluster_members
  -> cluster labeling worker or LLM
  -> surface_cluster_labels
  -> optional research hypotheses from labeled clusters
  -> OpenSearch safe projections
```

Incorrect flow:

```text
raw body / raw Burp request
  -> LLM
  -> finding
```

Incorrect flow:

```text
path contains "admin"
  -> service_class = admin
  -> finding
```

## Boundaries

### Surface Map is not Research Hypotheses

A surface cluster is not a hypothesis. It is a structural grouping.

Example:

```text
cluster: routes under /api/accounts with similar response shapes and object identifiers
```

This cluster may later support a hypothesis such as `possible_authz_sensitive_surface`, but the cluster itself is not a vulnerability candidate.

### Surface Map is not Findings

No Surface Map worker may create a row in `findings`.

Only an explicit triage/promote flow may create a finding.

### Surface Labels are not a Closed Enum

Labels are open strings:

```text
api_documentation_surface
seller_onboarding_portal
account_management_api
static_marketing_family
unknown_partner_backoffice
```

They may later be normalized by a separate canonical-label workflow, but the first version must not require a predefined taxonomy.

### LLM Labels Clusters, not Raw Endpoints

The LLM receives compact cluster summaries with evidence references. It does not read raw HTTP bodies, raw request bodies, cookies, Authorization headers, complete JWTs, complete base64 blobs, or arbitrary raw artifacts.

### OpenSearch is not Source of Truth

OpenSearch is used for search, filtering, faceting, and UI projections. It must be rebuildable from PostgreSQL.

## Existing Components to Reuse

Do not reimplement these from scratch:

- existing path normalization under `src/api/infrastructure/normalization/path_normalizer.py`;
- existing tests around path normalization;
- existing `research-engine` package for evidence packs, value shapes, gatekeeping, and research hypothesis writing;
- existing `search-indexer` service for rebuildable OpenSearch projections.

The Surface Map should reuse or wrap these components rather than creating duplicate logic.

## Safety Invariants

1. Raw HTTP bodies are not indexed into surface projections.
2. Raw Burp traffic is not sent to LLM.
3. Legacy `body_preview` is not automatically treated as safe.
4. `body_preview AS body_preview_safe` is not allowed in production LLM/research inputs.
5. `true AS safe_for_llm` blanket flags are not allowed in production LLM/research inputs.
6. A surface cluster is not a finding.
7. A surface label is not a finding.
8. A surface label is not a proof of vulnerability.
9. LLM output must be validated before persistence.
10. LLM output must contain evidence references for claims.
11. Active verification must go through `ActionService` and `PolicyService`.
12. Missing or ambiguous scope blocks active verification; it never allows by default.
13. OpenSearch state is disposable and rebuildable.
14. PostgreSQL state is authoritative.
15. Differential analysis across user accounts requires explicit authorized test principals and policy approval.
16. Principal graph overlap is only an authorization hypothesis, not proof of IDOR.

## Canonicalization and Dedup Strategy

Surface Map V1 starts with deterministic fingerprints before ML or embeddings.

Required fingerprints:

- `route_template`
- `route_fingerprint`
- `param_signature_fingerprint`
- `transport_fingerprint`
- `request_shape_fingerprint`
- `response_shape_fingerprint`
- `content_family_fingerprint`
- `feature_fingerprint`
- `node_fingerprint`
- `edge_fingerprint`
- `cluster_fingerprint`

The fingerprint inputs must not include raw secrets or unredacted raw values.

Examples:

```text
/users/123              -> /users/{number}
/users/456              -> /users/{number}
/users/550e8400-e29b... -> /users/{uuid}
/reset/eyJhbGciOi...    -> /reset/{token_like}
/docs/swagger-ui.css    -> /docs/{static_asset}
```

For V1, the system should prefer simple deterministic grouping:

- same route template;
- same response shape;
- same parameter signature;
- same body/content hash where already available;
- same host/prefix family;
- parent-child path relationship.

MinHash, SimHash, LSH, text embeddings, and graph embeddings are optional later layers. They should not block the first Surface Map implementation.


### Protocol and Transport Shape

Surface canonicalization must preserve protocol-level shape separately from
request/response content. This is required for later analysis of HTTP/1.1 versus
HTTP/2 versus HTTP/3, TLS versus cleartext, WebSocket surfaces, ALPN, QUIC,
multiplexing, keep-alive behavior, server-sent events, long polling, and other
long-lived/open-connection behavior.

Transport shape may contain bounded metadata such as:

- scheme: `http`, `https`, `ws`, `wss`;
- protocol family: `http`, `websocket`, `other`;
- port;
- observed HTTP version;
- TLS flag;
- ALPN token;
- transport protocol such as `tcp` or `quic`;
- bounded connection features such as `keep_alive`, `multiplexed`,
  `websocket_upgrade`, `server_sent_events`, or `long_polling`.

Transport shape is part of the feature fingerprint. Logical route identity should
separate scheme/protocol-family/port, but HTTP version and connection features
should remain feature-level material so the same logical route can still be
compared across HTTP versions.

### Nested Body Graphs and Entity Graphs

Request and response bodies can themselves be graphs. JSON, GraphQL, XML,
protobuf, thrift, AMF, and similar formats may contain deep object nesting,
references, arrays of entities, IDs, ownership hints, pagination structures, and
links between business objects. Surface Map V1 does not expand full body graphs.
It records only bounded body shape.

Follow-up TODO layers:

- `body_shape_graph`: safe structural graph for deeply nested request/response
  bodies, excluding raw values;
- `entity_model_graph`: inferred business entities and relationships from API
  traffic, response shapes, GraphQL selections, JSON/XML keys, forms, links, and
  repeated object identifiers;
- `principal_diff_graph`: differential graph comparison across explicitly
  authorized test principals/accounts. This can propose authorization hypotheses
  when one principal can observe or influence another principal's object graph.

`principal_diff_graph` must only run on targets and accounts that are explicitly
authorized by scope and policy. Its output is a candidate hypothesis, not proof
of IDOR. Active verification still goes through `ActionService` and
`PolicyService`.

## Graph Strategy

The Surface Map is a graph.

Node types are mechanical, not business classes. Initial V1 node types:

- `endpoint`
- `route_template`
- `response_shape`
- `content_family`

Later possible node types:

- `host`
- `service`
- `artifact`
- `parameter`
- `js_bundle`
- `redirect_target`
- `flow_step`

Initial V1 edge types:

- `endpoint_has_route_template`
- `endpoint_has_response_shape`
- `same_route_template`
- `same_response_shape`
- `same_param_signature`
- `same_content_family`
- `parent_route`

Later possible edge types:

- `links_to`
- `redirects_to`
- `discovered_from_js`
- `observed_after`
- `same_scan_batch`
- `similar_embedding`
- `same_auth_behavior`

Edge weights are explicit and versioned. The first clustering implementation may use connected components. Leiden/Louvain community detection can be introduced later once edge weights are stable.

## LLM Labeling Strategy

The LLM labels cluster summaries, not raw endpoints.

Input to the LLM should look like a compact, safe cluster summary:

```json
{
  "cluster_id": "...",
  "member_count": 18,
  "common_route_roots": ["/api/accounts"],
  "route_templates": [
    "GET /api/accounts/{number}",
    "POST /api/accounts/{number}/export"
  ],
  "common_tokens": ["api", "accounts", "export"],
  "common_value_classes": ["numeric_identifier"],
  "status_distribution": {"200": 12, "403": 3},
  "content_types": ["application/json"],
  "evidence_refs": ["..."]
}
```

Output from the LLM is a proposed label and explanation:

```json
{
  "label": "account_management_api",
  "confidence": 0.76,
  "risk_tags": ["object_level_authorization_sensitive", "data_export_surface"],
  "explanation": "The cluster contains account object routes and export actions.",
  "unknowns": ["Authentication and authorization behavior are not proven."],
  "evidence_refs": ["..."]
}
```

The label is not a finding. It may later contribute to research hypotheses.

## Temporal Novelty Strategy

Temporal intelligence is based on comparing snapshots.

Initial delta types:

- `node_added`
- `node_removed`
- `edge_added`
- `edge_removed`
- `cluster_added`
- `cluster_removed`
- `cluster_grew`
- `cluster_shrank`
- `status_transition`
- `response_shape_changed`
- `param_signature_changed`

V1 novelty score is allowed to be heuristic, but must be versioned.

Example scoring factors:

- new route template;
- transition from `403` to `200`;
- new state-changing route terms;
- new risky value shapes;
- new cluster;
- response shape changed.

Temporal deltas are still not findings. They are prioritization signals.

## OpenSearch Role

OpenSearch receives projections after PostgreSQL state exists.

Expected future indices:

- `bb-surface-nodes`
- `bb-surface-clusters`
- `bb-surface-deltas`
- `bb-research-hypotheses-current`

OpenSearch is used for:

- UI exploration;
- filtering and faceting;
- selecting candidates for further analysis;
- searching labels, tokens, route templates, fingerprints, and novelty scores.

OpenSearch must not be used for:

- source-of-truth cluster membership;
- triage state;
- finding promotion;
- raw evidence storage;
- direct raw LLM context.

## Economic Constraints

Surface Map V1 must be cheap enough for a personal VM.

V1 must avoid:

- comparing all endpoints with all endpoints;
- embedding every raw observation;
- running LLM on every endpoint;
- rebuilding the full graph on every single observation;
- storing raw body text in search projections.

V1 must prefer:

- deterministic fingerprints;
- bucketed comparisons;
- incremental rebuilds;
- batch execution;
- caching by fingerprint;
- LLM calls per cluster, not per endpoint.

## Caching Rules

Cache by fingerprint at every expensive boundary:

- route normalization result by raw path fingerprint;
- value-shape result by safe value fingerprint;
- response-shape result by normalized response metadata fingerprint;
- node identity by `node_fingerprint`;
- edge identity by `edge_fingerprint`;
- cluster identity by `cluster_fingerprint`;
- future embedding result by `feature_fingerprint`;
- future LLM label result by `cluster_summary_fingerprint + prompt_version + model_version`.

No cache key may include raw secrets.

## Non-goals for V1

- No fixed service taxonomy.
- No endpoint-by-endpoint LLM classification.
- No raw body indexing.
- No graph embeddings.
- No mandatory UMAP/HDBSCAN.
- No production LLM integration.
- No finding creation.
- No active verification.
- No OpenSearch-first architecture.

## Phase Plan

### Phase 1: PostgreSQL schema

Add:

- `surface_snapshots`
- `surface_nodes`
- `surface_edges`
- `surface_clusters`
- `surface_cluster_members`
- `surface_cluster_labels`
- `surface_deltas`

### Phase 2: canonical fingerprints

Implement route templates and safe fingerprints. Reuse the existing path normalizer.

### Phase 3: surface worker V1

Build snapshot, nodes, and deterministic edges from `http_observations`, `endpoints`, and `hosts`.

### Phase 4: clustering V1

Start with connected components. Add Leiden/Louvain only after weights are meaningful.

### Phase 5: cluster summaries

Build safe summaries for clusters.

### Phase 6: semantic labeling contract

Add `ClusterLabeler` interface, fixture labeler, label gatekeeper, and `surface_cluster_labels` writer.

### Phase 7: hypotheses from clusters

Create optional research hypotheses from labeled clusters through the existing research writer/gatekeeper flow.

### Phase 8: OpenSearch projections

Index surface nodes, clusters, deltas, and research hypotheses as rebuildable projections.

### Phase 9: temporal novelty

Compare snapshots and write deltas with versioned novelty scoring.

## Acceptance Criteria for Phase 0

- This ADR exists.
- It explicitly states that Surface Map is not a finding layer.
- It explicitly rejects fixed business enums as the primary strategy.
- It records PostgreSQL as source of truth.
- It records OpenSearch as rebuildable projection.
- It records cluster-first LLM labeling.
- It records fingerprint-based caching.
- It records that existing path normalization and value-shape extraction must be reused, not duplicated.
