# Bug bounty research platform: target architecture and implementation plan

> Статус в репозитории: утвержденная долгосрочная целевая архитектура.
>
> Этот документ определяет состояние, к которому должен прийти проект после
> завершения базового MVP. Описания текущей реализации внутри документа
> отражают снимок, использованный при его подготовке, и не заменяют
> [MVP gap audit](mvp-gap-audit.md). Порядок работ до MVP определяется
> [Patch plan to MVP](patch-plan-to-mvp.md). При расхождении сведений о том,
> что уже реализовано, источником истины является аудит текущей ветки.

Date: 2026-06-24

Status: architecture baseline + execution backlog

Scope: текущая кодовая база из `docker-compose.integration.zip`, распакованная в `/mnt/data/bb_code`, и согласованное целевое направление: typed graph, provenance, projections, metamorphic relations, bounded campaign executor, graph intelligence, LLM as constrained worker, human gate.

---

## 1. Executive summary

Кодовая база уже содержит реальный foundation, а не только набор идей. В ней есть control-plane, декларативный catalog, policy/scope/approval слой, transactional outbox, раннеры, ingestion, canonical facts, GraphFact/Neo4j projection, OpenSearch read model, Surface Engine MVP и зачатки agent/human workflow.

Но целевая система, которую нужно получить, пока не реализована полностью. Отсутствуют metamorphic relation DSL, campaign executor, request family planner, context-aware corpus generation, mutation planner, link prediction, spectral analysis, Hypothesis V2, vector scoring и полноценный human-in-loop на уровне аналитических кампаний.

Нужная стратегия: не переписывать базу. Достроить верхний аналитический слой поверх существующих `actions`, `policy`, `surface`, `graph`, `search`, `agent coordination`. LLM не должна становиться executor или source of truth. Она должна только предлагать кандидатов, объяснять triage, интерпретировать policy и писать черновики после validated evidence.

Главная формула целевого состояния:

```text
raw observations
  -> normalized facts
  -> typed graph + provenance
  -> projections
  -> deterministic analyzers
  -> metamorphic relations
  -> bounded campaign executor
  -> evidence graph
  -> human review
  -> state transitions
  -> report candidate
```

Анти-формула, которую нельзя строить:

```text
scanner output -> LLM -> payloads -> risk score -> report
```

---

## 2. What exists now

### 2.1 Repository shape

Observed repository snapshot:

```text
Python files: 382
Python LOC:   ~53,218
Tests:        72 test files
Main areas:   src/api, services/graph-projector, services/search-indexer,
              services/surface-engine, BugBountyDashBoard, alembic, tests
```

`python -m compileall -q src services tests` passes.

A full pytest run is not currently a reliable truth signal because the local execution environment misses some dependencies (`langgraph`, `psycopg2`) and because there is contract drift between tests and code in the agent wait/execution state area.

### 2.2 Control-plane

The control-plane is a strong part of the project.

Current components:

```text
src/api/application/contracts.py
src/api/application/*action* / orchestration services
src/api/application/pipeline/pipeline.yaml
src/api/infrastructure/events
src/api/infrastructure/orchestration
src/api/infrastructure/unit_of_work
alembic migrations for action/request/run/event/outbox state
```

The design already follows the correct path:

```text
ToolActionRequest
  -> catalog resolution
  -> policy/scope/approval
  -> PostgreSQL state
  -> transactional outbox
  -> RabbitMQ/worker
  -> runner
  -> raw artifact
  -> parser/processor/ingestor
  -> canonical facts
  -> OpenSearch / Neo4j / agent wait conditions
```

Important strengths:

- typed contracts for action/policy/tool invocation/result/artifact/status;
- separation of requested action and execution result;
- policy layer before runner execution;
- outbox/event pattern instead of direct side effects;
- catalog-driven capabilities and profiles;
- approval gates for active/sensitive profiles;
- `create_subprocess_exec`-style command invocation rather than shell string execution.

### 2.3 Catalog and policy

`src/api/application/pipeline/pipeline.yaml` defines capabilities and profiles for tools such as:

```text
subfinder
httpx
katana
playwright
gau / wayback-like URL discovery
linkfinder
ffuf
amass
dnsx / dnsx-ptr
subjack
asnmap
mapcidr
naabu
mantra
tlsx / smap / hakip2host-like services
worker graph
```

Profiles carry safety/scope/approval semantics. This is the right primitive. Future campaign execution must reuse it instead of bypassing it.

Policy layer already blocks command-like options such as:

```text
cmd
command
shell
exec
raw_command
nmap_cli
```

This must stay. Campaign executor must submit typed actions, not raw commands.

### 2.4 Runners and ingestion

Runners exist for discovery, validation, HTTP probing, crawling, URL extraction, JS analysis, fuzzing-like enumeration and infrastructure enrichment.

The runner layer should remain a low-level execution boundary. It should not absorb hypothesis logic or LLM logic.

Target relationship:

```text
Campaign planner -> ActionRequest -> existing policy -> existing runner -> artifact -> ingestor -> facts
```

Not:

```text
Campaign planner -> raw subprocess / shell / direct HTTP loop
```

### 2.5 Canonical facts and read models

The project already has several read-model directions:

- canonical facts in PostgreSQL;
- OpenSearch indexing via `services/search-indexer`;
- Neo4j projection via `services/graph-projector`;
- Surface Engine tables and snapshots;
- agent wait/projection readiness machinery.

This is the correct separation:

```text
PostgreSQL = source of truth
OpenSearch = search/read model
Neo4j = graph projection/read model
Surface Map = bounded shape/context model
LLM context = sanitized pointer-based summaries only
```

### 2.6 GraphFacts / Neo4j

GraphFacts are one of the strongest pieces.

Current relevant paths:

```text
services/graph-projector/graph_projector/contracts.py
services/graph-projector/graph_projector/ontology.yaml
services/graph-projector/graph_projector/*writer/query/template*
alembic/versions/*graph_fact*
```

Existing concepts include node facts, edge facts, graph fact batches, ontology validation, safe query templates and projection notifications.

Ontology already includes useful node types:

```text
Program
Scope
Host
IP
ASN
CIDR
Service
Endpoint
Parameter
JSFile
Tool
ToolRun
Artifact
Observation
Evidence
```

And useful edges:

```text
RESOLVES_TO
EXPOSES_SERVICE
HAS_ENDPOINT
HAS_PARAM
REFERENCES
PRODUCED_ARTIFACT
PRODUCED_OBSERVATION
DESCRIBES
SUPPORTS_EVIDENCE
DERIVED_FROM
```

This is enough to start deterministic graph intelligence. Do not jump directly to GNN/GDS before projections are stable.

### 2.7 Surface Engine

Surface Engine exists and is the right place to build endpoint/shape context.

Current relevant paths:

```text
services/surface-engine/surface_engine/canonicalize.py
services/surface-engine/surface_engine/nodes.py
services/surface-engine/surface_engine/postgres.py
services/surface-engine/README.md
alembic/versions/u1v2w3x4y5z6_add_surface_map.py
```

It already builds canonical endpoint and surface node drafts from HTTP observations.

Important safety property: surface nodes are shape-oriented. They should not contain raw bodies, raw headers, cookies, authorization material, secrets or large raw previews.

Current gap: migration already creates more tables than current code uses.

Tables present/planned by migration:

```text
surface_snapshots
surface_nodes
surface_edges
surface_clusters
surface_cluster_members
surface_cluster_labels
surface_deltas
```

Current code effectively writes snapshots/nodes. Edges, clusters, labels and deltas need implementation.

### 2.8 Search Indexer

`services/search-indexer/search_indexer/documents.py` builds safe OpenSearch documents and includes redaction limits. This is a good read-model layer for triage and dashboard search.

Keep it as a read model. Do not use OpenSearch as source of truth for evidence.

### 2.9 Hypotheses and critic

Current hypothesis layer exists but is MVP.

Relevant paths:

```text
src/api/application/hypotheses.py
src/api/application/hypothesis_critic.py
```

Current model:

- `HypothesisEvidenceRef` stores pointer-style evidence;
- `HypothesisCandidate` stores deterministic candidate;
- critic checks basic evidence/scope/impact/report draft readiness.

Main limitation: current builder uses simple evidence counting and scalar priority/confidence. It does not model:

- violated metamorphic relation;
- request family;
- campaign context;
- score vector;
- execution risk;
- novelty;
- impact prior;
- reproducibility;
- false-positive risk;
- human gate policy.

Do not mutate this layer into a large untyped blob. Add Hypothesis V2 рядом and bridge back into V1 only where UI compatibility requires it.

### 2.10 Agent / LangGraph / human loop

There is an early agent coordination layer:

```text
src/api/application/agent_wait_conditions.py
src/api/application/agent_coordination.py
src/api/application/*langgraph*
alembic/versions/*agent_coordination*
alembic/versions/*langgraph_checkpoints*
```

Current state: useful skeleton, not complete workflow engine.

Observed drift:

- tests expect wait/execution state classes that are not present;
- code supports limited wait conditions such as `new_facts_available` and `projections_ready`;
- LangGraph import paths require optional dependencies not always installed.

Target: use agent/human loop after deterministic planning, not as replacement for deterministic planning.

### 2.11 Frontend dashboard

Frontend exists under:

```text
BugBountyDashBoard/
```

Current issue: action mappings in `BugBountyDashBoard/src/services/api.js` drift from `pipeline.yaml` profile names.

Examples of likely mismatches:

```text
UI:   subfinder/passive-enumeration
YAML: subfinder/passive-recon

UI:   linkfinder/js-link-analysis
YAML: linkfinder/js-endpoint-extraction

UI:   mantra/js-secret-scan
YAML: mantra/js-secret-analysis

UI:   amass/active-enumeration, passive-enumeration
YAML: amass/active-enum, passive-enum

UI:   waymore/archive-url-discovery
YAML: no separate waymore capability; gau/wayback-like capability exists
```

Fix direction: frontend should not hardcode capability/profile IDs. It should render available actions from catalog metadata returned by API.

---

## 3. Main gaps

### 3.1 Runtime gaps

1. Frontend/catalog drift.
2. AnalysisService likely references legacy SQL views not created by current migrations.
3. Agent wait condition tests and runtime contracts are out of sync.
4. Some dependencies are duplicated or conflict-prone, especially around `psycopg2`/optional service dependencies.
5. Repository/archive contains `__pycache__` and `.pyc` artifacts.
6. Runner logging must be reviewed for leakage of targets, stdin, wordlists, tokens, cookies, and raw request material.
7. Command/process cleanup should be reviewed, especially unusual signal usage.

### 3.2 Architecture gaps

1. Surface edges/clusters/deltas not implemented.
2. No endpoint-param-object projection.
3. No metamorphic relation DSL.
4. No compiled relation validators.
5. No RequestFamily model.
6. No Campaign model.
7. No CampaignBudget / bounded executor.
8. No mutation planner.
9. No context-aware wordlist/schema generator.
10. No link prediction baseline.
11. No spectral layer.
12. No Hypothesis V2 score vector.
13. No full human gate around analytical campaigns.
14. No LLM proposal worker contract.
15. No dashboard views for relations/campaigns/evidence chains.

---

## 4. Target architecture

### 4.1 Core principle

Generation creates hypotheses.

Graph stores evidence.

State machine controls actions.

Metamorphic relations check violations.

Human review resolves ambiguity.

LLM accelerates semantics but does not own truth.

### 4.2 Target pipeline

```text
Scanner artifacts
  -> parsers / ingestors
  -> normalized observations
  -> canonical facts
  -> GraphFact batches
  -> Surface snapshots
  -> surface projections
  -> deterministic analyzers
  -> relation planner
  -> request family builder
  -> campaign budgeter
  -> dry-run / executor through existing ActionService
  -> relation check result
  -> evidence chain
  -> Hypothesis V2
  -> human review
  -> report candidate
```

### 4.3 LLM boundary

Allowed LLM roles:

1. Semantic expander: generate candidate endpoints, parameters, schema fields from sanitized context.
2. Relation proposer: propose relation specs in DSL, not executable network actions.
3. Triage summarizer: explain why a candidate matters.
4. Policy interpreter: compare candidate with program rules, but final decision stays deterministic/human.
5. Report drafter: write a draft only after validated evidence exists.

Forbidden LLM roles:

1. Direct executor.
2. Direct DB writer.
3. Direct RabbitMQ publisher.
4. Direct network client.
5. Severity authority.
6. Finding creator without evidence chain.
7. Scope authority.
8. Raw payload generator outside mutation classes and safety constraints.

### 4.4 State-machine model

Asset/fact state:

```text
discovered
  -> normalized
  -> scoped
  -> resolved
  -> probed
  -> fingerprinted
  -> enriched
  -> candidate_signal
  -> needs_human_review
  -> validated
  -> report_candidate
  -> submitted / ignored / suppressed / rescan_later
```

Campaign state:

```text
candidate_generated
  -> candidate_ranked
  -> schema_inferred
  -> metamorphic_family_built
  -> budget_assigned
  -> dry_run
  -> queued_for_execution
  -> executed
  -> relation_checked
  -> evidence_linked
  -> needs_human_review
  -> validated_signal
  -> suppressed_noise
  -> promoted_to_report_candidate
```

---

## 5. Target domain model

### 5.1 Existing entities to keep

Keep and build on:

```text
ActionRequest
PolicyDecision
ToolInvocation
ToolResult
ActionArtifactReference
GraphNodeFact
GraphEdgeFact
GraphFactBatch
SurfaceSnapshot
SurfaceNode
HypothesisEvidenceRef
HypothesisCandidate
CriticDecision
AgentWaitCondition
```

### 5.2 New entities

Add V1 metamorphic/campaign contracts:

```text
MetamorphicRelationSpec
RelationGuard
InputTransformSpec
OutputExpectationSpec
RequestFamilySpec
RelationCheckResult
CampaignSpec
CampaignBudget
CampaignExecutionPlan
CampaignStep
EvidenceChain
HypothesisV2
HypothesisScoreVector
HumanGatePolicy
SafetyClass
```

### 5.3 Hypothesis V2

```text
HypothesisV2:
  id
  program_id
  target_asset_ref
  graph_context_refs[]
  predicted_edges[]
  request_family_refs[]
  metamorphic_relation_refs[]
  expected_signal
  violated_relation_refs[]
  safety_class
  score_vector
  evidence_required
  evidence_chain_refs[]
  human_gate_policy
  state
  created_at
  updated_at
```

### 5.4 Score vector

Do not create one scalar `risk_score`.

Use vector scoring:

```text
HypothesisScoreVector:
  confidence          # likelihood that the hypothesis is real
  novelty             # how new/different this signal is
  impact_prior        # potential value if confirmed
  execution_risk      # scope/stability/rate-limit/safety risk
  evidence_strength   # reproducibility and quality of evidence
  false_positive_risk # expected noise probability
  review_urgency      # human queue priority
```

### 5.5 RequestFamily

```text
RequestFamilySpec:
  id
  program_id
  base_request_ref
  auth_context_refs[]
  object_context_refs[]
  transformations[]
  invariants[]
  stop_conditions[]
  safety_class
  budget_estimate
```

### 5.6 EvidenceChain

```text
EvidenceChain:
  id
  program_id
  observation_refs[]
  artifact_refs[]
  request_refs[]
  response_digests[]
  graph_fact_refs[]
  relation_check_result_refs[]
  diff_summary
  violated_relation
  reproducibility_score
  false_positive_risk
  safe_for_search
  safe_for_llm
```

---

## 6. Metamorphic testing design

### 6.1 Purpose

Metamorphic testing is not payload spraying. It solves the oracle problem by checking relations between related requests/responses when exact expected output is unknown.

Core form:

```text
source request
  -> transformed request(s)
  -> expected relation over responses
```

Relation shape:

```text
MetamorphicRelationSpec:
  id
  name
  guard
  transform
  expectation
  severity_hint
  safety_class
  scope_constraints
```

### 6.2 First safe relations

MVP relations:

1. QueryParameterOrderInvariant

```text
Guard:
  method == GET
  query_params_count >= 2
  endpoint is in scope
  no state-changing semantics detected

Transform:
  reorder query params

Expect:
  status class unchanged
  redirect class unchanged
  auth outcome unchanged
  response shape digest unchanged or compatible
```

2. HeadGetDisclosureInvariant

```text
Guard:
  method == GET
  endpoint allows HEAD or can be safely compared from observations

Transform:
  GET -> HEAD

Expect:
  HEAD must not reveal more structural or sensitive metadata than GET
```

3. EncodingNormalizationInvariant

```text
Guard:
  endpoint has safe path/query material
  no unsafe payload classes

Transform:
  equivalent URL encoding / normalization

Expect:
  auth outcome and object identity unchanged
```

4. PaginationMonotonicityInvariant

```text
Guard:
  endpoint is list-like
  pagination params inferred

Transform:
  page/cursor/window variation inside bounded budget

Expect:
  records remain within same filter/tenant/context
```

5. AuthBoundaryInvariant

```text
Guard:
  auth contexts available
  object ownership known
  endpoint sensitivity >= user_data

Transform:
  owner context -> non-owner same role context

Expect:
  non-owner receives 403/404 or equivalent non-disclosure response
```

AuthBoundaryInvariant must require human approval until the project has stable identity fixtures and scope proof.

### 6.3 Relation implementation rule

Relations must be compiled validators, not prompt text.

LLM may propose:

```text
relation name
applicability
transform class
expected output relation
reason
confidence
```

But execution requires:

```text
relation spec validation
scope validation
safety classification
budget assignment
compiled validator
human gate if needed
```

---

## 7. Context-aware corpus generation

### 7.1 Goal

Replace global wordlists with typed candidate spaces derived from context.

### 7.2 Candidate types

```text
EndpointCandidate(path, source, confidence, cluster_id, reason)
ParamCandidate(name, location, type_hint, source, confidence)
BodySchemaCandidate(shape, fields, constraints, source)
HeaderCandidate(name, value_class, reason)
StateTransitionCandidate(from_endpoint, to_endpoint, evidence)
```

### 7.3 Context sources

```text
scanner observations
HTTP corpus
forms / links / JS routes / fetch calls
GraphQL operations
OpenAPI / Swagger
sitemap / robots
framework/CMS/API gateway/cloud/auth provider fingerprints
graph neighbors
same ASN/CDN/CNAME/cert SAN/backend fingerprints
history / snapshot deltas
human review labels
```

### 7.4 LLM role

LLM can rank/generate candidates from sanitized context. It cannot execute. It returns typed candidates with reason and confidence. Deterministic validators decide whether a candidate enters a campaign.

---

## 8. Mutation and fuzzing design

### 8.1 Rule

Do not build a raw payload generator.

Build a mutation planner.

The mutation planner operates on mutation classes:

```text
type confusion
boundary value
encoding discrepancy
parser differential
normalization mismatch
authorization context switch
state replay
schema overposting
field omission
duplicate parameter ambiguity
pagination/window variation
content-type variation
API version variation
```

### 8.2 Safety classes

```text
observe_only
safe_differential
state_changing_low_risk
needs_human_approval
blocked
```

Default for new mutation class: `needs_human_approval` until tests and policy say otherwise.

### 8.3 Execution constraints

No mass enumeration.

No exfiltration.

No destructive testing.

No persistence unless explicitly approved and bounded.

No auth-bypass exploitation beyond minimal proof in authorized scope.

No direct raw HTTP loop outside ActionService/policy.

No LLM-generated request execution without deterministic validation.

---

## 9. Graph intelligence

### 9.1 Projections

Do not run graph algorithms on one untyped property graph.

Create specific projections:

```text
G_asset:
  org/domain/subdomain/ip/cidr/asn/service

G_http:
  host/endpoint/method/param/body-schema/response-shape

G_identity:
  user/role/tenant/object/auth-context

G_finding:
  signal/evidence/finding/root-cause/report

G_temporal:
  snapshot diffs / appeared / disappeared / changed

G_bipartite_endpoint_param:
  endpoints <-> params

G_bipartite_host_tech:
  hosts <-> technologies

G_bipartite_endpoint_object:
  endpoints <-> object types
```

### 9.2 Link prediction baseline

Start with simple algorithms:

```text
Jaccard
Common Neighbors
Adamic-Adar
Resource Allocation
bipartite matrix factorization
path/schema/behavior similarity ranker
```

Do not start with GNN.

Predicted edge types:

```text
endpoint likely handles entity
param likely controls object identity
service likely same_app_as service
host likely behind same backend
finding likely same_root_cause_as finding
API route likely exists but undiscovered
subdomain likely belongs_to program
```

### 9.3 Spectral analysis

Add after projections and baseline link prediction.

Use cases:

```text
app clusters
bridge assets
scope ambiguity boundaries
surface outliers
cluster drift between snapshots
weak components
high-centrality low-coverage campaign targets
```

Metrics:

```text
eigen-gap
Fiedler vector
conductance
Laplacian centrality
embedding outlier distance
cluster drift score
coverage per cluster
```

Neo4j GDS or external spectral jobs should be read-only and projection-bound.

---

## 10. Full implementation plan

## Phase P0 — Stabilize current runtime

Goal: make the existing system trustworthy before adding advanced analysis.

### P0.1 Frontend/catalog sync

Problem: dashboard hardcodes capability/profile IDs that drift from `pipeline.yaml`.

Actions:

- Add API endpoint: `GET /action-catalog` or reuse existing catalog read endpoint.
- Return capability/profile display metadata, safety level, approval requirement, input schema.
- Refactor dashboard to render actions from catalog.
- Remove hardcoded frontend action mappings.
- Add test: every displayed dashboard action must resolve against catalog.

Acceptance:

- No dashboard action can call a non-existing capability/profile.
- Profile rename in YAML does not require frontend code change.

### P0.2 AnalysisService view drift

Problem: analysis endpoints likely reference legacy views absent from migrations.

Actions:

- Inventory all SQL view names used by AnalysisService.
- Inventory all views created by migrations.
- Delete dead endpoints or rewrite them against current read models.
- Prefer OpenSearch/Graph query templates/Surface projections over legacy ad-hoc SQL.
- Ban dynamic view names unless whitelisted.

Acceptance:

- Fresh DB migration + API startup + all analysis endpoints smoke-tested.
- No missing relation/view errors.

### P0.3 Agent wait condition drift

Problem: tests and implementation disagree about wait/execution state.

Actions:

- Decide canonical wait conditions for M1:
  - `new_facts_available`
  - `projections_ready`
  - `tool_run_completed`
  - `ingestion_completed`
  - `campaign_relation_checked`
- Add missing state reader or update tests to current contract.
- Keep wait conditions pointer-based.

Acceptance:

- Agent wait condition tests pass without import drift.
- No optional LangGraph dependency required for non-agent tests.

### P0.4 Dependency and artifact hygiene

Actions:

- Remove `__pycache__` and `.pyc` from repo/archive.
- Add `.gitignore`/`.dockerignore` rules if missing.
- Normalize `psycopg2` dependencies.
- Separate optional extras:
  - `api`
  - `graph-projector`
  - `search-indexer`
  - `surface-engine`
  - `langgraph-agent`
  - `dev/test`

Acceptance:

- Clean checkout has no pyc files.
- `pip install -r requirements.txt` works for base API.
- Optional services install from their own requirements.

### P0.5 Runner safety review

Actions:

- Review command executor process group cleanup.
- Redact targets/stdin/wordlists/secrets in logs.
- Add structured audit events without raw sensitive content.
- Confirm all runners go through policy and catalog.

Acceptance:

- No runner logs raw authorization/cookie/token material.
- No raw shell command execution path.

### P0.6 CI smoke matrix

Actions:

- Add compileall job.
- Add unit test job without external services.
- Add contract test job.
- Add integration job with docker compose for PostgreSQL/RabbitMQ/OpenSearch/Neo4j as needed.

Acceptance:

- PR cannot merge if contracts drift.

---

## Phase P1 — Finish Surface Engine V1

Goal: make Surface Map usable as context and projection source.

### P1.1 Surface edges

Implement deterministic surface edges:

```text
host -> endpoint
endpoint -> route_template
endpoint -> request_shape
endpoint -> response_shape
endpoint -> param_signature
endpoint -> body_shape
endpoint -> transport_shape
observation -> endpoint
```

Code target:

```text
services/surface-engine/surface_engine/edges.py
services/surface-engine/surface_engine/postgres.py
```

Acceptance:

- Given fixture HTTP observations, engine writes nodes and edges.
- Edges are deterministic and idempotent.

### P1.2 Surface deltas

Implement snapshot diff:

```text
appeared
removed
changed
unchanged
```

Delta dimensions:

```text
new endpoint
removed endpoint
changed response shape
changed parameter signature
changed status/content-type class
new transport/service shape
```

Acceptance:

- Two fixture snapshots produce stable delta rows.

### P1.3 Surface clusters

Start simple:

- cluster by host/app fingerprint;
- cluster by route family;
- cluster by response shape family;
- cluster by technology/fingerprint when available.

Do not add spectral clustering yet.

Acceptance:

- Surface clusters are deterministic and explainable.

### P1.4 Surface projection exports

Expose projection builders:

```text
EndpointParamProjection
EndpointObjectProjection
HostTechProjection
EndpointResponseShapeProjection
EndpointTemporalProjection
```

Acceptance:

- Projections can be rebuilt from source tables.
- Projection rows carry provenance and snapshot IDs.

---

## Phase P2 — Metamorphic core V1

Goal: implement deterministic relation checking without active network execution.

### P2.1 Contracts

Add:

```text
src/api/application/metamorphic/contracts.py
```

Contracts:

```text
MetamorphicRelationSpec
RelationGuard
InputTransformSpec
OutputExpectationSpec
RelationCheckResult
RequestFamilySpec
SafetyClass
```

Acceptance:

- Contracts forbid raw payload blobs by default.
- Contracts are serializable and versioned.

### P2.2 Relation registry

Add:

```text
src/api/application/metamorphic/relation_registry.py
```

First validators:

```text
query_param_order_invariant
head_get_disclosure_invariant
encoding_normalization_invariant
```

Acceptance:

- Relations run against saved observation fixtures.
- Validators return pass/fail/inconclusive with reason.

### P2.3 Storage

Migration:

```text
metamorphic_relations
relation_check_results
request_families
```

Acceptance:

- Relation results are stored pointer-first.
- Raw response bodies are not copied into relation results.

### P2.4 API

Read-only endpoints first:

```text
GET /programs/{program_id}/metamorphic/relations
GET /programs/{program_id}/metamorphic/results
GET /programs/{program_id}/request-families
```

Acceptance:

- Dashboard can display relation results without executing anything.

---

## Phase P3 — Request family planner and budget dry-run

Goal: create bounded plans before execution.

### P3.1 Planner

Add:

```text
src/api/application/metamorphic/planner.py
```

Input:

```text
surface projection
relation registry
scope proof
policy context
```

Output:

```text
RequestFamilySpec[]
CampaignBudgetEstimate
```

Acceptance:

- Planner can produce dry-run families for safe relations.
- Every planned request has reason, relation, budget cost and safety class.

### P3.2 Budget engine

Add:

```text
src/api/application/metamorphic/budget.py
```

Budget dimensions:

```text
requests_per_host
requests_per_endpoint
requests_per_family
state_changing_requests_per_campaign
auth_context_switches
object_id_variants
novel_signal_per_100_requests
llm_generated_candidates_accepted_ratio
false_positive_rate_after_review
```

Acceptance:

- Budget can deny a campaign before execution.
- Budget result explains denial.

### P3.3 Human gate policy

Add:

```text
src/api/application/metamorphic/human_gate.py
```

Rules:

```text
auto-plan:
  observe_only
  safe_differential

human approval:
  state_changing_low_risk
  auth boundary involved
  tenant/object ownership involved
  confidence high but evidence weak

blocked:
  destructive potential
  out of scope
  missing scope proof
  mass enumeration risk
  exfiltration risk
```

Acceptance:

- No campaign can execute without safety classification and budget.

---

## Phase P4 — Campaign executor V1

Goal: execute only bounded, approved, safe campaign steps through existing ActionService.

### P4.1 Campaign model

Add migration:

```text
campaigns
campaign_steps
campaign_budget_events
campaign_execution_events
```

States:

```text
candidate_generated
candidate_ranked
schema_inferred
metamorphic_family_built
budget_assigned
dry_run
queued_for_execution
executed
relation_checked
evidence_linked
needs_human_review
validated_signal
suppressed_noise
promoted_to_report_candidate
```

Acceptance:

- Campaign state transitions are validated.
- Illegal transitions fail.

### P4.2 Executor adapter

Campaign executor must call existing `ActionService` with typed `ActionRequest`.

No direct HTTP loop.

No direct runner invocation.

No shell.

Acceptance:

- Every network action has an ActionRecord and policy decision.
- Every output artifact has provenance.

### P4.3 Quiescence and stop conditions

Stop campaign when:

```text
budget exhausted
novel signal rate drops
error rate rises
rate limit observed
scope uncertainty appears
human gate required
relation results inconclusive beyond threshold
```

Acceptance:

- Campaign cannot run unbounded.

---

## Phase P5 — Hypothesis V2 and EvidenceChain

Goal: promote relation violations and graph signals into reviewable hypotheses.

### P5.1 Hypothesis V2 contracts

Add:

```text
src/api/application/hypotheses_v2/contracts.py
```

Do not break current `hypotheses.py`.

Acceptance:

- V1 and V2 can coexist.
- V2 can export V1-compatible summary for existing UI if needed.

### P5.2 EvidenceChain builder

Add:

```text
src/api/application/evidence/chains.py
```

Evidence chain sources:

```text
observation refs
artifact refs
GraphFact refs
surface node refs
relation check results
campaign step refs
```

Acceptance:

- A hypothesis cannot become `report_candidate` without EvidenceChain.

### P5.3 Score vector

Implement deterministic score vector.

Start simple, transparent weights:

```text
confidence
novelty
impact_prior
execution_risk
evidence_strength
false_positive_risk
review_urgency
```

Acceptance:

- Score components are visible and explainable.
- No hidden scalar severity magic.

### P5.4 Critic V2

Extend deterministic critic:

```text
scope proof present
relation violated or graph signal supported
primary evidence present
reproducibility above threshold
unsafe content not exposed
impact claim supported
program policy compatibility checked
```

Acceptance:

- Report draft blocked unless critic passes.

---

## Phase P6 — Human review and agent loop

Goal: make human-in-loop part of state machine, not ad-hoc UI action.

### P6.1 Review queues

Queues:

```text
scope_ambiguity
relation_violation
campaign_approval
hypothesis_validation
report_candidate_review
suppression_review
```

Acceptance:

- Every human decision is stored with reason and provenance.

### P6.2 Agent wait conditions

Add wait conditions:

```text
campaign_relation_checked
human_review_completed
hypothesis_promoted
report_draft_ready
```

Acceptance:

- Agent workflows wait on pointer-based events.
- No raw bodies/secrets go into checkpoints.

### P6.3 Feedback loop

Human review updates:

```text
candidate generator weights
relation false-positive rate
suppression rules
scope decisions
future campaign budget
LLM candidate acceptance ratio
```

Acceptance:

- Review outcomes affect future ranking.

---

## Phase P7 — Context corpus and wordlist generation

Goal: generate typed candidates from context, not generic wordlists.

### P7.1 Candidate generator

Add:

```text
src/api/application/corpus/contracts.py
src/api/application/corpus/generator.py
src/api/application/corpus/ranker.py
```

Candidate types:

```text
EndpointCandidate
ParamCandidate
BodySchemaCandidate
HeaderCandidate
StateTransitionCandidate
```

Acceptance:

- Candidates have source, reason, confidence and scope.
- Candidates are deduplicated and ranked.

### P7.2 Deterministic generators first

Sources:

```text
existing paths
JS route extraction
OpenAPI/Swagger if found
forms
sitemaps
robots
neighbor endpoint lexicon
surface cluster lexicon
historical params
```

Acceptance:

- Useful candidates without LLM.

### P7.3 LLM semantic expander later

LLM input:

```text
sanitized surface context
route templates
param names
response shapes
technology labels
program policy summary
```

LLM output:

```text
typed candidates
reason
confidence
relation suggestion
safety class suggestion
```

Acceptance:

- LLM output cannot execute directly.
- Candidate must pass deterministic validation.

---

## Phase P8 — Link prediction baseline

Goal: rank likely missing edges and useful campaign targets.

### P8.1 Projection tables

Materialize:

```text
endpoint_param_projection
host_tech_projection
endpoint_object_projection
endpoint_response_shape_projection
host_endpoint_projection
finding_evidence_projection
```

Acceptance:

- Projections are rebuildable from source facts.

### P8.2 Baseline algorithms

Implement:

```text
common neighbors
Jaccard
Adamic-Adar
Resource Allocation
path similarity
schema similarity
behavior similarity
temporal co-change
```

Acceptance:

- Predicted edges are ranked and explainable.
- Each predicted edge has feature contributions.

### P8.3 Human labels

Use review labels as training/evaluation data.

Acceptance:

- Precision@K tracked per predicted edge type.

---

## Phase P9 — Spectral analysis

Goal: detect clusters, outliers, bridge assets and drift.

### P9.1 Precondition

Do not start until:

- Surface clusters exist.
- Projection tables exist.
- Link prediction baseline exists.
- Rebuild process is deterministic.

### P9.2 Spectral jobs

Implement offline job, not inline request path.

Metrics:

```text
eigen-gap
Fiedler vector
conductance
Laplacian centrality
cluster drift
outlier distance
coverage per cluster
```

Acceptance:

- Spectral result stores feature/projection version.
- Human can inspect why a cluster/outlier was flagged.

### P9.3 Neo4j GDS boundary

If Neo4j GDS is used:

- read-only jobs;
- no arbitrary Cypher;
- projection-specific templates;
- audit logs;
- versioned outputs.

Acceptance:

- GDS cannot mutate source graph.

---

## Phase P10 — LLM workers

Goal: add LLM after deterministic substrate exists.

### P10.1 LLM context builder

Build sanitized context packets:

```text
program policy summary
surface cluster summary
endpoint family summary
candidate list
relation result summaries
evidence pointer summaries
```

Never include raw secrets, cookies, auth headers, full bodies or unredacted artifacts.

### P10.2 LLM workers

Workers:

```text
semantic_expander
relation_proposer
triage_summarizer
policy_interpreter
report_drafter
```

### P10.3 LLM output validation

Every output must pass schema validation.

No free-form action execution.

No direct report submission.

Acceptance:

- Invalid LLM output is rejected.
- LLM cannot bypass human gate.

---

## Phase P11 — Dashboard and operator UX

Goal: show operators the actual state machine and evidence.

### P11.1 New views

Add dashboard sections:

```text
Surface Map
Metamorphic Relations
Campaigns
Relation Violations
Hypotheses V2
Evidence Chains
Human Review Queue
Graph Intelligence
LLM Suggestions
```

### P11.2 Explainability

For every hypothesis show:

```text
why this target
which relation
which evidence
which graph path
score vector
risk gates
budget used
human actions available
```

Acceptance:

- Operator can tell why a candidate exists without reading logs.

---

## Phase P12 — Reporting and submission workflow

Goal: produce report candidates only from validated evidence.

### P12.1 Report candidate model

Fields:

```text
title
summary
scope proof
impact claim
steps to reproduce
minimal proof
affected assets
evidence chain refs
limitations
policy compatibility
redaction status
```

### P12.2 Report draft gate

No draft unless:

```text
critic passed
scope proof exists
evidence chain exists
reproducibility score above threshold
human validation exists for ambiguous cases
```

Acceptance:

- Report draft never invents exploitability.
- Draft cites evidence pointers only.

---

## Phase P13 — Production hardening

### P13.1 Observability

Metrics:

```text
actions_created_total
actions_blocked_total
actions_requires_approval_total
campaigns_started_total
campaigns_stopped_by_budget_total
relation_checks_total
relation_violations_total
hypotheses_promoted_total
human_acceptance_rate
false_positive_rate
novel_signal_per_100_requests
projection_rebuild_duration
outbox_lag
runner_error_rate
```

### P13.2 Security controls

Controls:

```text
strict scope mode by default
rate limits
per-program quotas
approval for state-changing actions
artifact redaction
secret scanning before indexing/LLM
audit log for every execution decision
```

### P13.3 Rebuildability

Every read model must be rebuildable:

```text
OpenSearch index
Neo4j graph
Surface projections
Graph intelligence outputs
Spectral outputs
```

Acceptance:

- Disaster recovery can rebuild from PostgreSQL canonical state and artifact pointers.

---

## 11. File and module layout proposal

```text
src/api/application/metamorphic/
  __init__.py
  contracts.py
  relation_registry.py
  validators.py
  planner.py
  budget.py
  human_gate.py
  repositories.py

src/api/application/campaigns/
  __init__.py
  contracts.py
  state_machine.py
  executor.py
  repositories.py
  scoring.py

src/api/application/evidence/
  __init__.py
  chains.py
  contracts.py
  redaction.py

src/api/application/hypotheses_v2/
  __init__.py
  contracts.py
  builder.py
  critic.py
  scoring.py
  promotion.py

src/api/application/corpus/
  __init__.py
  contracts.py
  deterministic_generator.py
  llm_expander.py
  ranker.py

src/api/application/graph_intelligence/
  __init__.py
  projections.py
  link_prediction.py
  spectral.py
  scoring.py

services/surface-engine/surface_engine/
  edges.py
  deltas.py
  clusters.py
  projections.py
```

Migrations:

```text
add_surface_edges_runtime_support
add_metamorphic_relations
add_request_families
add_campaigns
add_evidence_chains
add_hypotheses_v2
add_graph_intelligence_outputs
```

Docs:

```text
docs/adr/metamorphic-campaign-graph-intelligence-v1.md
docs/superpowers/specs/metamorphic-campaign-v1.md
docs/superpowers/plans/metamorphic-campaign-v1.md
docs/architecture/target-platform-v2.md
docs/security/llm-boundaries.md
docs/security/campaign-safety-policy.md
```

---

## 12. Test strategy

### 12.1 Unit tests

Targets:

```text
contracts serialization
relation validators
budget decisions
state machine transitions
score vector calculation
surface canonicalization
projection builders
```

### 12.2 Contract tests

Targets:

```text
catalog/profile resolution
frontend action IDs vs catalog
policy decision statuses
GraphFact ontology validation
Surface node/edge schema
metamorphic relation schema
LLM output schema
```

### 12.3 Fixture-based metamorphic tests

Use saved request/response fixtures.

No network.

Relations:

```text
query param order
HEAD/GET metadata
encoding normalization
pagination monotonicity
response shape stability
```

### 12.4 Integration tests

With docker compose:

```text
PostgreSQL
RabbitMQ
OpenSearch
Neo4j
API
Graph projector
Search indexer
Surface engine
```

Test paths:

```text
action -> artifact -> ingestor -> fact -> OpenSearch
fact -> GraphFact -> Neo4j
HTTP observation -> surface snapshot -> surface edges -> deltas
relation result -> evidence chain -> Hypothesis V2
campaign dry-run -> budget denial/approval
```

### 12.5 Safety tests

Abuse cases:

```text
raw shell option submitted
out-of-scope target
unsafe mutation class
missing scope proof
state-changing campaign without approval
LLM tries to request execution
LLM produces invalid relation spec
artifact contains secret-like material
raw body attempts to enter LLM context
```

Acceptance:

- All blocked with explicit reason.

---

## 13. Metrics and quality gates

### 13.1 Engineering gates

```text
compileall passes
unit tests pass
contract tests pass
migration from empty DB passes
frontend catalog test passes
no pyc artifacts
no raw secret logs
```

### 13.2 Research quality gates

```text
novel_signal_per_100_requests
human_acceptance_rate
false_positive_rate
relation_violation_reproducibility
precision@K for predicted edges
campaign_stop_reason_distribution
coverage per surface cluster
```

### 13.3 Safety gates

```text
scope proof required
budget required
safety class required
human approval for risky classes
LLM cannot execute
raw artifacts cannot enter LLM context
report candidate requires evidence chain
```

---

## 14. Risk register

### Risk: LLM becomes hidden executor

Impact: unsafe actions, irreproducible findings, scope violations.

Mitigation: LLM only returns typed proposals. ActionService remains execution boundary.

### Risk: campaign layer becomes noisy fuzzing engine

Impact: target disruption, bans, useless findings.

Mitigation: budget, stop conditions, safety classes, human gate.

### Risk: Graph ML produces opaque recommendations

Impact: untrusted triage, poor operator adoption.

Mitigation: start with explainable link prediction features; store feature contributions.

### Risk: spectral analysis over unclean graph gives garbage

Impact: false clusters/outliers.

Mitigation: wait for Surface V1/projections; version every projection.

### Risk: read models become source of truth

Impact: rebuild inconsistency.

Mitigation: PostgreSQL canonical state and artifact refs remain source of truth.

### Risk: dashboard displays stale or impossible actions

Impact: broken UX and operator errors.

Mitigation: catalog-driven frontend.

### Risk: evidence leaks secrets

Impact: security incident.

Mitigation: redaction before indexing, LLM context builder, pointer-only evidence.

---

## 15. Non-goals for first implementation wave

Do not implement in P0-P4:

```text
full autonomous agent
raw payload generator
Neo4j GDS production jobs
GNN
direct browser exploitation workflow
report auto-submission
mass enumeration
state-changing fuzzing without approval
LLM network access
```

---

## 16. Recommended immediate next commits

1. Add this document as project plan.
2. Add ADR for metamorphic/campaign/graph-intelligence architecture.
3. Fix frontend catalog drift.
4. Fix AnalysisService view drift.
5. Fix agent wait condition drift.
6. Remove pyc/pycache artifacts.
7. Add Surface Engine edges/deltas tests.
8. Add metamorphic contracts with no execution.
9. Add `QueryParameterOrderInvariant` validator on fixtures.
10. Add `RelationCheckResult` storage.
11. Add `HypothesisScoreVector` contract.
12. Add campaign dry-run budget model.

---

## 17. Final target definition

The project is successful when the platform can:

1. ingest scanner artifacts into normalized, provenance-backed facts;
2. rebuild OpenSearch, Neo4j and Surface projections from source of truth;
3. build typed surface projections per program and snapshot;
4. generate safe request families from deterministic context;
5. check metamorphic relations using compiled validators;
6. run only bounded, policy-approved campaigns;
7. convert violations into evidence chains;
8. promote evidence chains into Hypothesis V2 with vector scoring;
9. ask a human only at meaningful ambiguity/risk points;
10. use LLM only for semantic expansion, relation proposals, triage explanation, policy interpretation and report drafting;
11. explain every finding candidate through graph path, relation result, evidence chain, budget and human decision.

In one sentence:

```text
A safe bug bounty research platform where scanners collect facts, graph/surface projections structure them, metamorphic relations test behavioral invariants, campaigns execute only within bounded policy, humans resolve ambiguity, and LLMs assist without controlling truth or execution.
```
