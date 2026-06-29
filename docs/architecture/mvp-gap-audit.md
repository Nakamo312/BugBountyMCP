# MVP Gap Audit

Status: draft audit for `codex/apply-latest-patches`

Date: 2026-06-24

Source roadmap: [Patch plan to MVP](patch-plan-to-mvp.md)

This audit maps the current integration branch against the MVP roadmap. It is
not a replacement for the patch plan; it is the working checklist for what is
already present, what is only partially implemented, and what remains missing.

## Status Legend

- `Done` - implemented with visible code and tests or docs that match the
  roadmap acceptance intent.
- `Partial` - useful foundation exists, but acceptance criteria are incomplete
  or naming/API shape differs from the roadmap.
- `Missing` - no meaningful implementation found in the current branch.
- `Blocked/Risk` - implementation exists in a form that conflicts with a hard
  ordering rule or needs a decision before continuing.

## Current Verification Baseline

Current Python verification:

```bash
.\.tmp_pytest\Scripts\python.exe -m pytest -q
```

Result: `409 passed, 15 skipped` on June 24, 2026. The skipped set includes
the PostgreSQL outbox concurrency/retry contracts added for live integration
acceptance.

Docker is not installed in the current environment, so this audit did not run
Docker smoke tests, frontend build, live RabbitMQ integration, live Neo4j
integration, or live OpenSearch integration.

## Executive Summary

| Area | Status | Notes |
| --- | --- | --- |
| Phase 0 architecture docs | Done | Target architecture, patch plan, root agent index, docs index, control-plane and refactor roadmap docs are present. |
| M1 execution core | Partial | Action contracts, policy, typed profile options, execution ceilings, bounded campaign expansion/lifecycle, catalog, scheduler, jobs/runs, transactional outbox, work keys, and `/tool-actions` routes exist. Live PostgreSQL/RabbitMQ acceptance and remaining attempts/leases decisions are incomplete. |
| M2 artifact storage cleanup | Partial | Content-addressed storage, gzip compression and queryable retention classes exist; previews, sanitization persistence and lineage remain incomplete. |
| M3 remove research-engine | Done | Standalone `services/research-engine` and its compose service are removed; sanitizer helpers remain in application code. |
| M4 Neo4j graph projection | Partial | GraphFact contracts, ontology, Neo4j projector, graph_fact_batches, apply loop, raw-artifact/http-observation/canonical-inventory enqueuing through rebuild, safe query templates, dedupe, notifications, and writer hardening exist. Remaining gaps are richer producer coverage and runtime smoke. |
| M5 OpenSearch expansion | Partial | Search-indexer exists with safe document builders, schema versioning, projection lag/readiness, endpoint/technology projections, and hypothesis projection; later roadmap indexes remain deferred. |
| M6 async agent protocol | Partial | Durable workflow/inbox/wait/result-set schema, EventStore routing, all five planned wait predicates including `campaign_quiescent`, automatic wait processing, claim/lease, cancellation boundary, internal-token guarded REST protocol, and auth/claim/handoff/cancel smoke coverage exist. Remaining work is live runtime smoke against real Postgres/LangGraph services. |
| M7 LangGraph workflows | Partial | The compiled pointer-only `StateGraph` durably interrupts for readiness and is automatically resumed after its wait condition resolves. Live end-to-end integration remains. |

## Phase 0 - Architecture Baseline

Status: `Done`

Evidence:

- [target-platform.md](target-platform.md)
- [patch-plan-to-mvp.md](patch-plan-to-mvp.md)
- [control-plane.md](control-plane.md)
- [refactor-roadmap.md](refactor-roadmap.md)
- [Root AGENTS.md](../../AGENTS.md)
- [docs/README.md](../README.md)

Gaps:

- None for the documentation baseline.

Next action:

- Keep this audit linked from the documentation index and update it after every
  milestone-sized integration.

## M1 - Stabilize Execution Core

Overall status: `Partial`

### 0009 Execution Contracts

Status: `Partial`

Evidence:

- `ActionRequest`, `ActionSubmission`, `PolicyDecision`, and `ToolInvocation`
  exist in [contracts.py](../../src/api/application/contracts.py).
- `ToolInvocation` carries action/job/run/program/capability/profile/targets/
  options/effective-budget/safety/scope/policy/campaign/correlation fields.
- Contract tests exist under [tests/application](../../tests/application/) and
  [tests/infrastructure](../../tests/infrastructure/).

Gaps:

- Roadmap names are `ToolActionRequest` and `ToolActionAccepted`, while the
  current code uses `ActionRequest` and `ActionSubmission`.
- Decide whether to rename, alias, or explicitly document the naming difference.

Next action:

- Add a compatibility test or alias that makes the roadmap terminology explicit:
  `ToolActionRequest = ActionRequest` and `ToolActionAccepted = ActionSubmission`,
  or rename the public DTOs if that is the desired API.

### 0010 Capability Catalog Schema

Status: `Partial`

Evidence:

- Capability/catalog code exists in [capability_catalog.py](../../src/api/application/capability_catalog.py),
  [action_catalog.py](../../src/api/application/action_catalog.py), and
  [tool_catalog](../../src/api/infrastructure/tool_catalog/).
- Catalog migrations and snapshot tests exist:
  [v2w3x4y5z6a7_materialize_tool_catalog_snapshots.py](../../alembic/versions/v2w3x4y5z6a7_materialize_tool_catalog_snapshots.py),
  [y5z6a7b8c9d0_action_catalog_entry_id.py](../../alembic/versions/y5z6a7b8c9d0_action_catalog_entry_id.py),
  [test_capability_catalog_manifest_snapshot.py](../../tests/application/test_capability_catalog_manifest_snapshot.py),
  [test_tool_catalog_projection_schema.py](../../tests/infrastructure/test_tool_catalog_projection_schema.py).

Gaps:

- The exact roadmap tables `tool_capabilities`, `tool_profiles`,
  `tool_profile_options`, `tool_safety_classes`, `tool_input_schemas`, and
  `tool_output_schemas` are not yet confirmed as separate durable tables.
- Unknown-option and dangerous-option rejection needs to be tied to the durable
  catalog acceptance criteria.

Next action:

- Write a catalog schema audit test that asserts the durable schema and option
  validation behavior required by the roadmap.

### 0011 Policy Split

Status: `Partial`

Evidence:

- Policy service exists in [policy.py](../../src/api/application/services/policy.py).
- Scope-related pipeline code exists in [scope_policy.py](../../src/api/application/pipeline/scope_policy.py).
- Tests exist in [test_policy_split.py](../../tests/application/test_policy_split.py).

Gaps:

- Need confirm concrete separation into `CapabilityPolicy`, `ScopePolicy`,
  `RiskPolicy`, and `ApprovalPolicy`, not only behavior inside one service.
- Need explicit acceptance tests proving scope check occurs before job creation.

Next action:

- Add tests around blocked active targets and approval-required active profiles
  at the action creation boundary.

### 0012 Action Request Schema V2

Status: `Partial`

Evidence:

- Durable tables exist for `action_request_targets`,
  `action_request_options`, `scope_decisions`, `approval_requests`,
  `approval_decisions`, and `campaigns` in [orm.py](../../src/api/infrastructure/adapters/orm.py).
- Migration exists:
  [w3x4y5z6a7b8_action_request_schema_v2.py](../../alembic/versions/w3x4y5z6a7b8_action_request_schema_v2.py).
- Tests exist:
  [test_action_request_schema_v2.py](../../tests/infrastructure/test_action_request_schema_v2.py),
  [test_action_schema_v2_contracts.py](../../tests/application/test_action_schema_v2_contracts.py).

Gaps:

- Need confirm blocked actions never create jobs across all policy paths.
- `/tool-actions` exists as an alias; durable schema and stored request naming
  still use `ActionRequest`.

Next action:

- Add an integration test for blocked action persistence: durable blocked state,
  no `jobs` row, no live run.

### 0013 Jobs, Runs, Leases, Attempts Schema

Status: `Partial`

Evidence:

- `jobs` and `runs` exist in [orm.py](../../src/api/infrastructure/adapters/orm.py).
- `runs` includes `claim_key`, `work_key`, lease fields, retry fields, and
  execution status handling.
- Lease and retry behavior exists in [orchestration/store.py](../../src/api/infrastructure/orchestration/store.py).

Gaps:

- Separate roadmap tables `tool_runs`, `node_runs`, `run_attempts`,
  `run_leases`, `run_errors`, and `run_metrics` are not present as separate
  first-class tables.
- Retry attempt records are represented inside `runs`, not clearly separated
  into attempt history.

Next action:

- Decide whether current `runs` schema is the accepted MVP simplification or
  implement the missing separate attempt/lease/error/metric tables.

### 0014 Transactional Outbox Schema And Store

Status: `Done`

Evidence:

- `event_store` and `event_dispatches` exist in [orm.py](../../src/api/infrastructure/adapters/orm.py).
- Event dispatch claiming exists in [orchestration/store.py](../../src/api/infrastructure/orchestration/store.py).
- Allowed action state, initial job/run, event, and pending delivery are written
  by one transaction.
- Event/destination uniqueness prevents duplicate outbox rows.
- [Transactional outbox ADR](../adr/event-store-dispatches-outbox.md) accepts
  this pair as the MVP outbox and documents at-least-once delivery semantics.
- Tests exist:
  [test_event_store_dispatch_contract.py](../../tests/application/test_event_store_dispatch_contract.py),
  [test_event_dispatcher.py](../../tests/application/test_event_dispatcher.py),
  and [test_event_dispatch_outbox.py](../../tests/integration/test_event_dispatch_outbox.py).

Next action:

- Run the PostgreSQL integration contract in the isolated compose stack.

### 0015 Outbox Publisher Service

Status: `Partial`

Evidence:

- Event dispatcher code exists in [dispatcher.py](../../src/api/infrastructure/events/dispatcher.py).
- Dispatch records support attempts, status, locks, and dispatch timestamps.
- The dispatcher is wired into API startup, listens for PostgreSQL
  notifications, and retains periodic sweeping as recovery.
- Unit tests cover publish success, failure retry, and agent-router failure.
- An integration contract covers competing claims and retry preservation.

Gaps:

- The PostgreSQL integration contract is present but cannot run in the current
  environment because Docker is unavailable.
- A live RabbitMQ publish/retry acceptance test remains.

Next action:

- Run PostgreSQL and RabbitMQ integration acceptance in the isolated compose
  stack.

### 0016 Tool Execution API V2

Status: `Partial`

Evidence:

- Action REST route exists in [actions.py](../../src/api/presentation/rest/routes/actions.py).
- `POST /actions` and `POST /tool-actions` route to the same control-plane
  action creation handler and return `202`.
- `GET /actions/{id}` and `GET /tool-actions/{id}` return the same stored
  action read model.
- `GET /actions/{id}/events` and `GET /tool-actions/{id}/events` return stored
  event-store records linked to the action.
- `GET /actions/{id}/result` and `GET /tool-actions/{id}/result` return the
  current action status, readiness, run summaries, and artifact references
  without loading raw artifact bodies. This is an execution aggregate, not the
  M6 agent result-set model.
- The `/actions` prefix remains available for existing dashboard/internal
  callers while `/tool-actions` satisfies the public MVP terminology.
- Legacy scan route file is deleted in the staged branch.

Gaps:

- Roadmap says legacy `/scan/*` routes become wrappers; current branch removes
  the scan route instead.
- Literal outbox naming and publisher runtime acceptance remain unresolved.

Next action:

- Finish the M1 outbox publisher/runtime acceptance and settle whether removed
  legacy scan routes need temporary compatibility wrappers.

### 0017 Runner ToolInvocation Propagation

Status: `Done`

Evidence:

- ToolInvocation builder exists in [invocation.py](../../src/api/application/pipeline/invocation.py).
- Worker invocation tests exist in [test_worker_invocation.py](../../tests/application/test_worker_invocation.py).
- Runner acceptance tests in
  [test_runner_tool_invocation_options.py](../../tests/application/test_runner_tool_invocation_options.py)
  prove typed options reach `httpx`, `katana`, `ffuf`, and `naabu`
  `CommandExecutor` calls.
- Profile manifests define strict option schemas, defaults, and hard ceilings
  for the first four runner families.
- `ActionService` applies defaults and resolves request/profile/system ceilings
  before policy evaluation and job creation.
- The effective budget is included in the action event, initial `runs.run_payload`,
  and reconstructed `ToolInvocation`.
- Runner arguments clamp supported timeout, rate, and concurrency values to the
  effective budget.
- The four runner paths construct argument lists and do not accept raw shell
  command strings.

Gaps:

- Distributed rate limiting across workers is not implemented.
- Campaign-level budget consumption accounting is not implemented.
- Fanout, depth, and cooldown enforcement remains in patch 0018.

Next action:

- Add campaign accounting only after the local action/runner ceilings are
  accepted as the execution boundary.

### 0018 Worker Idempotency And Work Key

Status: `Partial` - implementation complete, live PostgreSQL acceptance pending.

Evidence:

- `work_key` exists on `runs`.
- Work key generation exists in [fingerprints.py](../../src/api/application/pipeline/fingerprints.py).
- Scheduled node registry uses work keys in [registry.py](../../src/api/application/pipeline/registry.py).
- Store code handles active work and coalesced triggers.
- Worker manifests define cooldown, fanout, expansion depth, and token cost.
- `EventEnvelope` and `PipelineContext` preserve `campaign_id` and increment
  `expansion_depth` across downstream events.
- Campaign work keys include `campaign_id`.
- `campaigns` stores run/target limits, consumption counters, token capacity,
  available tokens, refill rate, and refill timestamp.
- `claim_node_run` applies depth, cooldown, run/target budget, and token-bucket
  checks before inserting a scheduled run.
- Budget consumption and run insertion are atomic; duplicate/coalesced/retry
  paths do not consume budget twice.
- Unit and schema tests exist in
  [test_campaign_expansion_limits.py](../../tests/application/test_campaign_expansion_limits.py),
  [test_campaign_budget_claims.py](../../tests/infrastructure/test_campaign_budget_claims.py),
  and [test_campaign_budget_schema.py](../../tests/infrastructure/test_campaign_budget_schema.py).
- A live concurrency contract exists in
  [test_campaign_budget_concurrency.py](../../tests/integration/test_campaign_budget_concurrency.py).

Gaps:

- The concurrent PostgreSQL contract has not been run in the current
  Docker-less environment.

Next action:

- Run the integration contract, then continue with patch 0019 campaign
  lifecycle and quiescence.

### 0019 Campaign Lifecycle

Status: `Partial` - implementation complete, live PostgreSQL acceptance pending.

Evidence:

- `campaigns` table exists with status, program, correlation, and workflow
  fields.
- `ActionRequest` carries `campaign_id`, `correlation_id`, and `workflow_id`.
- Initial work activates `running`; downstream scheduled work activates
  `expanding`.
- `CampaignActivityState` and deterministic lifecycle evaluation cover
  `created`, `running`, `expanding`, `waiting_for_projections`, `quiescent`,
  `closed`, `cancelled`, and `failed`.
- The existing wait-condition sweep reconciles active campaigns.
- Activity checks cover active runs, pending outbox deliveries, graph
  projection events, GraphFact batches, and program-level projection lag.
- The quiet window defaults to 30 seconds.
- `campaign_quiescent` is implemented in the existing wait engine and uses the
  same lifecycle reader as background reconciliation.
- A live PostgreSQL contract exists in
  [test_campaign_lifecycle_quiescence.py](../../tests/integration/test_campaign_lifecycle_quiescence.py).

Gaps:

- The lifecycle integration contract has not been run in the current
  Docker-less environment.
- Projection readiness remains program-scoped, so another campaign for the same
  program can conservatively delay quiescence.

Next action:

- Run the integration contract, then continue with the next MVP patch.

## M2 - Artifact Storage Cleanup

Overall status: `Partial`

Evidence:

- Raw artifact storage/repository/reconciler code exists under
  [artifacts](../../src/api/infrastructure/artifacts/).
- Raw artifact parser services exist under [services](../../src/api/application/services/)
  and [parsers](../../src/api/infrastructure/parsers/).
- Sanitizer helpers exist in [sanitizer.py](../../src/api/application/research/sanitizer.py).
- Сырой вывод инструмента хранится как адресуемый по SHA-256 NDJSON. Одинаковые
  потоки событий используют один физический файл, а каждая строка
  `raw_artifacts` сохраняет собственный контекст программы, запуска и
  инструмента.
- Сначала завершаются файл и строка метаданных, затем сохраненные события
  построчно передаются парсеру.
- Старые NDJSON-артефакты со встроенными метаданными остаются доступными для
  повторного разбора.
- Крупные артефакты от 1 МиБ сохраняются как детерминированный gzip, при этом
  SHA-256 продолжает описывать исходный канонический NDJSON.
- `raw_artifacts` хранит `content_encoding`, физический размер и индексируемый
  `retention_class`; повторный разбор прозрачно читает сжатые файлы.
- При записи создаются ограниченный внутренний preview и очищенный preview с
  версиями sanitizer/политики. Сырой preview всегда имеет
  `raw_safe_for_llm=false`.
- Чувствительные HTTP-заголовки, bearer-токены, пары секретов и JSON-поля
  очищаются до выставления `sanitized_safe_for_llm=true`.
- LangGraph и OpenSearch artifact-preview projection выбирают только разрешенные
  очищенные preview и не получают raw preview или `storage_uri`.
- Raw artifact хранит явные parser/scope/target/parent ссылки; связь с tool run
  остается в `run_id`.
- Канонические HTTP observations и JavaScript references связывают результаты
  парсера с raw artifact существующими внешними ключами.
- Sanitized preview связан с тем же raw artifact и версиями sanitizer/policy.

Gaps:

- Live PostgreSQL migration acceptance for the completed M2 artifact schema is
  implemented in `tests/integration/test_artifact_storage_m2.py`, but remains
  unexecuted in the current environment because Docker/PostgreSQL is not
  available.

Next action:

- Run the prepared M2 PostgreSQL acceptance in CI or an environment with the
  isolated integration database; do not block the next roadmap patch on the
  local absence of Docker.

## M3 - Remove Research Engine Service

Overall status: `Done`

Evidence:

- Standalone `services/research-engine` has been deleted.
- `docker-compose.yml` no longer defines a `research-engine` service.
- Research-related sanitizer helpers remain under
  [src/api/application/research](../../src/api/application/research/) for
  artifact safety and redaction.
- Contract coverage exists in
  [test_m3_research_engine_removal.py](../../tests/test_m3_research_engine_removal.py).

Gaps:

- Hypothesis, evidence, critic/verifier and report workflows remain future M6/M7
  work and must not be reintroduced as a standalone pseudo-intelligence service.

Next action:

- Continue with M1 outbox/API naming gaps and M4 graph producers/rebuild/query
  templates before starting durable agent workflow work.

## M4 - Neo4j Graph Projection

Overall status: `Partial`

### Done / Strong Foundation

Evidence:

- Graph projector service exists under [services/graph-projector](../../services/graph-projector/).
- Neo4j Docker/profile config exists in [docker-compose.yml](../../docker-compose.yml).
- GraphFact contracts exist in [contracts.py](../../services/graph-projector/graph_projector/contracts.py).
- Ontology files exist:
  [ontology.py](../../services/graph-projector/graph_projector/ontology.py),
  [ontology.yaml](../../services/graph-projector/graph_projector/ontology.yaml).
- Neo4j writer/upsert exists in [writer.py](../../services/graph-projector/graph_projector/writer.py).
- Batch store/applicator exist:
  [batch_store.py](../../services/graph-projector/graph_projector/batch_store.py),
  [applicator.py](../../services/graph-projector/graph_projector/applicator.py).
- Raw artifact GraphFact producer/enqueuer exists in
  [raw_artifacts.py](../../services/graph-projector/graph_projector/producers/raw_artifacts.py).
- Canonical inventory GraphFact producer exists in
  [canonical_inventory.py](../../services/graph-projector/graph_projector/producers/canonical_inventory.py).
  It projects current PostgreSQL Host/IP/Service state without
  `source_artifact_id` and `tool_run_id`; this is intentionally not an evidence
  path.
- HTTP observation GraphFact producer/enqueuer exists for lineage-backed
  `httpx`, `katana`, `ffuf`, and `playwright` observations in
  [http_observations.py](../../services/graph-projector/graph_projector/producers/http_observations.py).
  It emits asset facts plus evidence-path facts:
  `Artifact -> PRODUCED_OBSERVATION -> Observation -> DESCRIBES -> Host/IP/Service/Endpoint`.
- Query parameter facts are covered for source-backed HTTP observations:
  `Endpoint -> HAS_PARAM -> Parameter` and
  `Observation -> DESCRIBES -> Parameter`. Parameter values are not projected
  into Neo4j by default.
- JavaScript reference graph facts are covered for source-backed
  `javascript_references` rows:
  `JSFile -> REFERENCES -> Endpoint` and
  `Artifact -> PRODUCED_OBSERVATION -> Observation -> DESCRIBES -> JSFile/Endpoint`.
  Referenced query strings are not projected into Neo4j by default.
- LinkFinder ingestion persists extracted endpoint references into the canonical
  `javascript_references` table when run/artifact lineage is available.
- Graph producers no longer use hard-coded tool allowlists. New tools such as
  `arjun` can project through the existing canonical observation type when the
  row has non-empty `source_tool`, `program_id`, `run_id`, and `raw_artifact_id`.
- Inventory facts such as hosts, IPs, host-IP links, and basic services are
  projected from canonical state. Full evidence paths are reserved for
  source-backed observations, hypotheses, findings, and reportable risk claims,
  not ordinary asset inventory.
- Graph rebuild service and CLI command exist in
  [rebuild.py](../../services/graph-projector/graph_projector/rebuild.py) and
  [__main__.py](../../services/graph-projector/graph_projector/__main__.py).
- Safe graph query templates exist in
  [query_templates.py](../../services/graph-projector/graph_projector/query_templates.py):
  `endpoint_neighborhood`, `asset_exposure`, `hidden_endpoints_from_js`,
  `exposed_services_by_technology`, `evidence_path`, and
  `hypothesis_evidence_paths`.
- GDS readiness is represented as a prerequisite check in
  [gds_readiness.py](../../services/graph-projector/graph_projector/gds_readiness.py).
- Migrations exist for graph batches, dedupe, projection events, and
  notifications.
- `graph_projection_events` has a table-level PostgreSQL notification trigger,
  so new ready events wake the existing projection event loop without adding
  per-source compose services.
- A single projection-event worker entry point exists in
  [projection_events.py](../../services/graph-projector/graph_projector/projection_events.py).
  It processes the registered `graph_projection_events` handlers together and
  can listen to `graph_projection_events_changed`; per-source compose services
  are intentionally not part of the runtime shape.
- Tests exist for contracts, ontology, Neo4j upsert, batch store, apply service,
  graph projection events, the projection-event worker, raw artifact producer,
  enqueue command, canonical inventory producer, rebuild, safe query templates,
  and GDS readiness.
- Current e2e graph coverage verifies GraphFact projection into plain Neo4j for
  canonical HTTP observations, the shared projection-event worker path, and
  canonical inventory rebuild. It does not cover Neo4j GDS, clustering,
  similarity, or named analytical projections.

Remaining gaps:

- `0032` infra-tool producer coverage has the canonical host/IP/service
  projection path. Lightweight history remains open only for mutable state such
  as open ports and technology versions.
- Katana and Playwright can still add richer source URL coverage for JavaScript
  references beyond LinkFinder output.
- Docker runtime smoke for graph profile still needs to be run in an environment
  with Docker available.
- Neo4j GDS is intentionally out of M4 and remains post-MVP/M8 work. It must
  not be treated as present infrastructure until named projection contracts,
  safe query templates, and rebuild semantics exist.

Next action:

- Finish the remaining M4 producer coverage, then run graph profile smoke.

## M5 - OpenSearch Expansion

Overall status: `Partial`

Evidence:

- Search-indexer service exists under [services/search-indexer](../../services/search-indexer/).
- OpenSearch and dashboards services exist in [docker-compose.yml](../../docker-compose.yml).
- Document builders and OpenSearch client exist in
  [documents.py](../../services/search-indexer/search_indexer/documents.py) and
  [opensearch_client.py](../../services/search-indexer/search_indexer/opensearch_client.py).
- Existing documents and static mappings carry `schema_version` and
  `sanitizer_version`; relevant documents expose canonical artifact/tool-run
  identifiers.
- Static `bb-endpoints` and `bb-technologies` mappings and canonical
  PostgreSQL producers exist. Both support program-scoped reads.
- Technology documents contain normalized technology names only; arbitrary
  source JSON values are not indexed.
- Artifact preview projection count uses the same safe-preview predicate as its
  source query, preventing false projection lag.
- Durable per-program projection watermarks are maintained by PostgreSQL source
  triggers and program-scoped reindex runs. Application-level readiness rejects
  missing, failed, lagging, or mismatched projection states.
- `bb-research-hypotheses` projects `research_hypotheses` and linked
  `research_hypothesis_evidence` for the MVP research workflow. It indexes
  status, scores, fingerprints, evidence metadata, and only evidence text marked
  `safe_for_search`.
- LangGraph accesses hypothesis search through a bounded context tool, not raw
  OpenSearch DSL. The tool requires `program_id`, clamps `limit`, validates
  status and `hypothesis_type`, and returns only search-safe hypothesis fields.
- `HypothesisSelectionPolicy` turns search-safe hypothesis hits into bounded
  next-step decisions (`build_evidence`, `critic_review`, `draft_report`,
  `refresh_evidence`, `duplicate_review`, `defer`) without promoting findings
  or executing tools.

Gaps:

- Remaining roadmap indexes beyond MVP hypotheses need canonical sources and an
  MVP consumer before implementation.

Next action:

- Keep packages/CVE/OSINT/secrets/agent-event indexes deferred until their
  canonical sources and first consumers are ready.

## M6 - Async Agent Protocol

Overall status: `Partial`

Evidence:

- Durable coordination schema exists for `agent_workflows`,
  `agent_workflow_runs`, `agent_subscriptions`, `agent_inbox`,
  `agent_wait_conditions`, and `agent_result_sets`.
- `agent_subscriptions` are scoped by program/campaign/correlation and
  `agent_inbox` writes are protected by a unique `dedupe_key`.
- `AgentEventRouter` routes matching EventStore envelopes into
  `AgentInboxStore.enqueue_once` and is wired into the existing durable
  `EventDispatcher`.
- `AgentWaitConditionEngine` can evaluate `projections_ready` using the M5
  projection readiness reader.
- `AgentWaitConditionEngine` evaluates `new_facts_available` against
  program-scoped `agent_result_sets` using action/campaign/workflow selectors.
- `AgentWaitConditionEngine` evaluates `tool_run_completed` from terminal
  program-scoped run state and `ingestion_completed` from the successful
  post-ingestion `flushing -> completed` transition.
- `AgentWaitConditionProcessor` persists `resolved` and `timed_out`
  transitions through `AgentWaitConditionStore`.
- The processor runs with application lifecycle, automatically resumes
  `mvp-research` graphs after an atomic `pending -> resolved` transition, and
  retries resolved waits while their durable workflow run remains `waiting`.
- `AgentProtocolStore` exposes durable operations for subscriptions, inbox
  claim/lease, inbox ack, wait-condition creation/listing, and result-set
  upsert/list by action/campaign/workflow scope.
- Claimed inbox messages hand off to LangGraph through deterministic thread IDs:
  existing workflow runs resume by `workflow_run_id`, while new messages use the
  stable `agent-inbox:<message_id>` thread key. Ack happens only after the graph
  checkpoint already exists or the start/resume call succeeds.
- `ResearchInboxProcessor` wires this boundary as an optional background
  worker. It claims only its configured subscription `inbox_key`, opens a
  request-scoped `ResearchControlGraph`, records handoff failures in
  `agent_inbox.last_error` without releasing the active lease, and leaves
  retry/checkpoint lifecycle to LangGraph instead of adding a second inbox retry
  runtime. Each sweep can now return and emit a single structured summary
  (`claimed`, `started`, `resumed`, `already_started`,
  `skipped_terminal_workflow`, `failed`, `acknowledged`) so operators can see
  whether the worker is starting new research passes, resuming existing ones,
  deduplicating old messages, or only encountering handoff failures without
  logging one line per inbox message.
- REST routes under `/api/v1/agent` expose the M6 agent protocol without raw
  execution shortcuts. The router is guarded by an explicit internal boundary:
  callers must send an allowed `X-Agent-Actor` and, unless the dev bypass is
  explicitly enabled, a matching `X-Agent-Internal-Token`. Workflow cancellation
  persists the workflow/run terminal state, cancels pending subscriptions/inbox/wait
  edges for the run, and inbox handoff refuses to resume terminal workflow runs.

Gaps:

- 0040 is implemented at schema/store level.
- 0041 is implemented through the existing EventStore dispatcher.
- 0042 has `tool_run_completed`, `ingestion_completed`, `projections_ready`,
  result-set-backed `new_facts_available`, `campaign_quiescent`, timeout
  persistence, and cancellation call paths.
- 0043 has result-set storage/upsert/list by stable result key and
  action/campaign/workflow scope.
- 0044 has subscriptions, inbox claim/lease, inbox ack, workflow cancellation,
  wait-condition, result-set REST APIs, and an internal actor/token boundary.

Next action:

- Run the agent protocol smoke against real Postgres/LangGraph runtime services, not
  only in-process fakes.

## M7 - LangGraph Workflows To MVP

Overall status: `Partial`

Evidence:

- `LangGraphWorkflowRuntime` exists as an application-layer skeleton that can
  start, pause, resume, and cancel workflow runs by stable IDs and
  `checkpoint_ref`.
- `LangGraphWorkflowStore` persists workflow/run status through existing
  `agent_workflows` and `agent_workflow_runs` tables.
- Workflow state stores IDs and pointers (`action_ids`, `wait_condition_ids`,
  `result_set_keys`, `checkpoint_ref`), not raw artifacts or response bodies.
- `LangGraphContextTools` exposes read-only program context, result set fetch,
  OpenSearch sanitized search, bounded hypothesis search/selection, safe graph
  template rendering, and sanitized artifact previews while denying raw artifact
  access.
- `CypherGateway` is restricted to explicit admin/debug use, blocks write
  clauses and `CALL`, enforces `$program_id`, wraps reads with an outer
  `LIMIT`, clamps timeout, executes through a Neo4j read executor, and records
  hashed query/parameter audit rows. Agent/runtime graph access uses registered
  graph templates via `LangGraphContextTools`.
- `LangGraphToolActionTool` creates existing `ActionRequest` contracts and
  delegates to `ActionService.request_action`; it has no RabbitMQ, runner, or
  direct persistence authority.
- `LangGraphApprovalNode` coordinates approval-required actions with workflow
  pause/resume/cancel semantics while delegating approve/reject decisions to the
  existing `ActionService`.
- `HypothesisBuilderWorkflow` consumes existing result-set references and stores
  manual-verification candidates in `research_hypotheses` with linked
  `research_hypothesis_evidence`; it does not write finding rows.
- `HypothesisCriticWorkflow` checks missing evidence, program-boundary scope,
  unsafe artifact content, and unsupported impact before report drafting.
- `ReportDraftBuilderWorkflow` links evidence refs, redacts authorization,
  cookie, token, and session values in both body and evidence-chain text, and
  blocks draft completion when evidence or critic acceptance is missing.
- `ResearchPass` reuses the existing builder, critic, and report builder
  in one typed application flow. It returns stored hypothesis IDs, critic
  decisions, drafts, and a safe summary (`empty`, `needs_evidence`,
  `drafts_ready`, etc.) without creating findings.
- `ResearchControlGraph` compiles that flow with LangGraph 1.2.6, persists
  thread checkpoints through the official PostgreSQL saver, and supports
  asynchronous state recovery/resume. When bounded hypothesis selection is
  wired in, it records selected next-step pointers such as `critic_review`,
  `build_evidence`, or `draft_report`; graph state still contains only request
  pointers, hypothesis IDs, critic statuses, draft statuses, finding IDs,
  safe pass summary counters, and selected step metadata, not report bodies
  or evidence text.
- `ResearchReadinessGate` reuses M6 projection and result-set readers,
  persists stable wait conditions, updates durable workflow run state, and
  drives LangGraph interrupt/resume without calling execution transports. It
  now emits explicit readiness reason codes such as `projection_missing`,
  `projection_lagging`, `projection_failed`, `result_sets_not_ready`, and
  `durable_wait_requires_workflow_run` so the graph can distinguish why it
  is waiting instead of storing only free-form reason text.
- `ResearchWaitResumer` restores the compiled graph from its PostgreSQL
  checkpoint by workflow-run thread ID; manual `aresume()` calls are no longer
  required in the normal runtime path. It checks workflow-run status before
  resume and skips terminal runs (`completed`, `failed`, `cancelled`) so stale
  wait rows cannot revive cancelled or completed research passes.
- `ResearchInboxBridge` keeps inbox delivery and graph execution
  separated: the inbox provides claim/lease and ack, while the research graph owns
  start/resume execution through deterministic checkpoint thread IDs. Bridge
  results now carry explicit outcomes (`started`, `resumed`, `already_started`,
  `skipped_terminal_workflow`) plus machine-readable reason codes for skipped
  terminal workflow runs.
- Alembic owns the pinned LangGraph PostgreSQL checkpoint schema; application
  startup does not run third-party schema setup dynamically.

Gaps:

- 0045 skeleton is implemented at runtime/store level.
- 0046 is implemented as a read-only context facade over existing read models;
  live OpenSearch/Neo4j smoke and richer context shaping remain.
- 0047 is implemented as a minimal read-only Cypher Gateway; live Neo4j smoke
  and richer procedure allowlists remain.
- 0048 is implemented as an API/application-service-only ToolActionRequest
  wrapper for LangGraph.
- 0049 is implemented as a thin approval node over existing control-plane
  approval and workflow runtime state.
- 0050 is implemented as a deterministic hypothesis builder workflow over
  existing result-set references and research hypothesis/evidence tables.
- 0051 is implemented as a deterministic critic/verifier workflow.
- 0052 is implemented as a redacted, evidence-linked report draft workflow.
- The semantic stages are connected through `ResearchPass` and compiled
  through `ResearchControlGraph`.
- The graph now pauses before research until required named projections and a
  matching result set are available, then rechecks readiness on resume.
- A live PostgreSQL checkpoint round-trip remains unverified because Docker is
  unavailable in the current environment.

Next action:

- Run the PostgreSQL checkpoint round-trip and complete controlled-loop
  integration with the existing execution/projection services before declaring
  the whole MVP done.

## Recommended Next Milestones

1. Commit the current integration branch after final verification.
2. Complete M1 outbox/publisher/API naming gaps.
3. Complete remaining M4 graph producer coverage and graph profile smoke.
4. Complete M5 projection lag/readiness.
5. Complete remaining M6 auth boundaries.
6. Run M7 PostgreSQL checkpoint and controlled-loop integration smoke.

## Open Decisions

- Should `/actions` remain permanently as a dashboard/internal alias after
  `/tool-actions` is treated as the public MVP name?
- Should `event_dispatches` be documented as the MVP outbox implementation, or
  should literal `event_outbox`/`event_inbox` tables be added?
- Should M2 artifact storage cleanup stay in MVP, or be explicitly deferred?
- Should `ActionRequest`/`ActionSubmission` be renamed or aliased to roadmap
  `ToolActionRequest`/`ToolActionAccepted`?
- Should current `runs` table remain the MVP representation for attempts,
  leases, errors, and metrics, or should the separate roadmap tables be added?
