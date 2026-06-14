# MVP Gap Audit

Status: draft audit for `codex/apply-latest-patches`

Date: 2026-06-14

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

Last known Python verification before this audit:

```bash
python -m pytest -q
```

Result reported in this branch: `137 passed`.

This audit did not run Docker smoke tests, frontend build, RabbitMQ integration,
Neo4j integration, or OpenSearch integration.

## Executive Summary

| Area | Status | Notes |
| --- | --- | --- |
| Phase 0 architecture docs | Done | Target architecture, patch plan, root agent index, docs index, control-plane and refactor roadmap docs are present. |
| M1 execution core | Partial | Action contracts, policy, catalog, scheduler, jobs/runs, event dispatch, and work keys exist, but outbox/publisher, explicit `/tool-actions`, attempts/leases schema, budgets, and quiescence are incomplete. |
| M2 artifact storage cleanup | Partial | Raw artifact metadata/storage and sanitizer helpers exist, but content-addressed storage, compression, retention, previews, and lineage model are not complete. |
| M3 remove research-engine | Missing / Blocked | `services/research-engine` and the compose service still exist. This violates the roadmap target until removed or frozen with tests. |
| M4 Neo4j graph projection | Partial | GraphFact contracts, ontology, Neo4j projector, graph_fact_batches, apply loop, raw-artifact enqueuer, dedupe, notifications, and writer hardening exist. Producers, rebuild, and query templates remain. |
| M5 OpenSearch expansion | Partial | Search-indexer exists with safe document builders, but missing-index expansion, schema versioning, document producers, and projection lag are incomplete. |
| M6 async agent protocol | Missing | No durable agent workflow/inbox/wait-condition/result-set implementation found. |
| M7 LangGraph workflows | Missing | No LangGraph runtime, checkpointer, read tools, approval node, hypothesis workflow, critic, or report builder found. |

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
  options/safety/scope/policy/campaign/correlation fields.
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
- API naming still uses `/actions`, not the planned `/tool-actions`.

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

Status: `Partial`

Evidence:

- `event_store` and `event_dispatches` exist in [orm.py](../../src/api/infrastructure/adapters/orm.py).
- Event dispatch claiming exists in [orchestration/store.py](../../src/api/infrastructure/orchestration/store.py).
- Tests exist:
  [test_event_store_dispatch_contract.py](../../tests/application/test_event_store_dispatch_contract.py),
  [test_event_dispatcher.py](../../tests/application/test_event_dispatcher.py).

Gaps:

- Literal `event_outbox` and `event_inbox` tables from the roadmap are not
  present.
- Need prove action/policy/scope/job/run/outbox are written atomically in one
  transaction.
- Need prove duplicate outbox events are prevented by idempotency key.

Next action:

- Define whether `event_dispatches` is the MVP outbox replacement. If yes,
  update docs/tests to say so. If no, add `event_outbox` and publisher tests.

### 0015 Outbox Publisher Service

Status: `Partial`

Evidence:

- Event dispatcher code exists in [dispatcher.py](../../src/api/infrastructure/events/dispatcher.py).
- Dispatch records support attempts, status, locks, and dispatch timestamps.

Gaps:

- Need RabbitMQ publisher integration acceptance tests.
- Need concurrent publisher tests proving no double-publish with lock/lease
  behavior.
- Need failure retry test at the transport boundary.

Next action:

- Add a fake RabbitMQ publisher test around dispatcher claim, publish failure,
  retry, and success marking.

### 0016 Tool Execution API V2

Status: `Partial`

Evidence:

- Action REST route exists in [actions.py](../../src/api/presentation/rest/routes/actions.py).
- `POST /actions` returns `202` and action catalog endpoints exist.
- Legacy scan route file is deleted in the staged branch.

Gaps:

- Planned API path is `/tool-actions`, but current implementation exposes
  `/actions`.
- Planned `GET /tool-actions/{id}/events` and
  `GET /tool-actions/{id}/result` are not confirmed.
- Roadmap says legacy `/scan/*` routes become wrappers; current branch appears
  to remove the scan route instead.

Next action:

- Decide final public path. If `/actions` is intentional, update roadmap
  terminology. Otherwise add `/tool-actions` routes and keep `/actions` as an
  alias or dashboard-internal path.

### 0017 Runner ToolInvocation Propagation

Status: `Partial`

Evidence:

- ToolInvocation builder exists in [invocation.py](../../src/api/application/pipeline/invocation.py).
- Worker invocation tests exist in [test_worker_invocation.py](../../tests/application/test_worker_invocation.py).

Gaps:

- Need acceptance tests proving typed options reach `httpx`, `katana`, `ffuf`,
  and `naabu` runner command builders.
- Need confirm all runner command construction stays shell-safe argument lists.

Next action:

- Add runner-specific propagation tests for the four required tools.

### 0018 Worker Idempotency And Work Key

Status: `Partial`

Evidence:

- `work_key` exists on `runs`.
- Work key generation exists in [fingerprints.py](../../src/api/application/pipeline/fingerprints.py).
- Scheduled node registry uses work keys in [registry.py](../../src/api/application/pipeline/registry.py).
- Store code handles active work and coalesced triggers.

Gaps:

- Fanout limits, depth limits, cooldown, token bucket, and campaign budget
  fields are not fully confirmed.

Next action:

- Add explicit budget/fanout/depth tests before expanding scheduler behavior.

### 0019 Campaign Lifecycle

Status: `Partial`

Evidence:

- `campaigns` table exists with status, program, correlation, and workflow
  fields.
- `ActionRequest` carries `campaign_id`, `correlation_id`, and `workflow_id`.

Gaps:

- Need lifecycle engine for `created`, `running`, `expanding`,
  `waiting_for_projections`, `quiescent`, `closed`, `cancelled`, `failed`.
- Need quiescence detection across outbox/jobs/projection lag and quiet window.

Next action:

- Implement campaign status transitions only after outbox/publisher and
  projection lag states are made explicit.

## M2 - Artifact Storage Cleanup

Overall status: `Partial`

Evidence:

- Raw artifact storage/repository/reconciler code exists under
  [artifacts](../../src/api/infrastructure/artifacts/).
- Raw artifact parser services exist under [services](../../src/api/application/services/)
  and [parsers](../../src/api/infrastructure/parsers/).
- Sanitizer helpers exist in [sanitizer.py](../../src/api/application/research/sanitizer.py).

Gaps:

- No confirmed content-addressed artifact blob store.
- No confirmed compression and retention policy model.
- No confirmed artifact preview and sanitized-preview persistence.
- No complete artifact lineage model with parser/sanitizer/source/scope/tool-run
  references.

Next action:

- Decide whether M2 remains in MVP. The current patch plan includes it; if the
  team wants to defer it, update [patch-plan-to-mvp.md](patch-plan-to-mvp.md)
  explicitly and keep raw artifacts as immutable referenced evidence.

## M3 - Remove Research Engine Service

Overall status: `Missing / Blocked`

Evidence:

- [services/research-engine](../../services/research-engine/) still exists.
- `docker-compose.yml` still contains a `research-engine` service.
- Research-related application sanitizer code exists under
  [src/api/application/research](../../src/api/application/research/).

Gaps:

- Roadmap requires no standalone `research-engine` service.
- Need inventory useful pieces, freeze standalone expansion, and remove compose
  references.

Next action:

- Make M3 the next implementation milestone after committing the current
  integration branch: inventory, freeze tests, remove service, remove compose
  entry, keep only explicitly approved sanitizer/shared utilities.

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
- Migrations exist for graph batches, dedupe, projection events, and
  notifications.
- Tests exist for contracts, ontology, Neo4j upsert, batch store, apply service,
  graph projection events, raw artifact producer, and enqueue command.

Remaining gaps:

- `0032` infra-tool producers for subfinder/dnsx/naabu/httpx are not complete.
- `0033` web/API producers for katana/linkfinder/nuclei/playwright observations
  are not complete.
- `0034` graph rebuild command is not found.
- `0035` safe graph query templates are not found.
- Docker runtime smoke for graph profile has not been run.

Next action:

- After M3, finish M4 in this order: producers, rebuild command, query
  templates, then graph profile smoke.

## M5 - OpenSearch Expansion

Overall status: `Partial`

Evidence:

- Search-indexer service exists under [services/search-indexer](../../services/search-indexer/).
- OpenSearch and dashboards services exist in [docker-compose.yml](../../docker-compose.yml).
- Document builders and OpenSearch client exist in
  [documents.py](../../services/search-indexer/search_indexer/documents.py) and
  [opensearch_client.py](../../services/search-indexer/search_indexer/opensearch_client.py).

Gaps:

- Need schema-versioned indexes.
- Need target indexes listed in the roadmap.
- Need sanitized and bounded producers for artifacts/http/endpoints/technologies/
  hypotheses.
- Need projection watermarks and lag state.

Next action:

- Do not start M6 until M5 exposes a reliable `projections_ready` signal for
  agent wait conditions.

## M6 - Async Agent Protocol

Overall status: `Missing`

Evidence:

- No durable `agent_workflows`, `agent_workflow_runs`, `agent_subscriptions`,
  `agent_inbox`, `agent_wait_conditions`, or `agent_result_sets` tables were
  found.
- No AgentEventRouter implementation was found.

Gaps:

- All M6 patches remain to be implemented.

Next action:

- Start M6 only after M1 outbox/publisher and M5 projection lag are explicit.

## M7 - LangGraph Workflows To MVP

Overall status: `Missing`

Evidence:

- No LangGraph runtime, checkpointer, workflow service, read-only context tools,
  Cypher gateway, ToolActionRequest tool, approval node, hypothesis builder,
  critic/verifier workflow, or report builder workflow was found.

Gaps:

- All M7 patches remain to be implemented.

Next action:

- Do not implement LangGraph until M6 wait/resume protocol is durable and
  projection readiness can be queried.

## Recommended Next Milestones

1. Commit the current integration branch after final verification.
2. Complete M3 research-engine removal because it currently conflicts with a
   hard roadmap rule.
3. Complete M1 outbox/publisher/API naming gaps.
4. Complete M4 graph producers, rebuild, and query templates.
5. Complete M5 projection lag/readiness.
6. Start M6 agent protocol.
7. Start M7 LangGraph workflows.

## Open Decisions

- Should public API terminology become `/tool-actions`, or is `/actions` the
  accepted product/API name?
- Should `event_dispatches` be documented as the MVP outbox implementation, or
  should literal `event_outbox`/`event_inbox` tables be added?
- Should M2 artifact storage cleanup stay in MVP, or be explicitly deferred?
- Should `ActionRequest`/`ActionSubmission` be renamed or aliased to roadmap
  `ToolActionRequest`/`ToolActionAccepted`?
- Should current `runs` table remain the MVP representation for attempts,
  leases, errors, and metrics, or should the separate roadmap tables be added?
