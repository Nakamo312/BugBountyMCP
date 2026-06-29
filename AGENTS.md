# BugBountyMCP Agent Index

This is the root navigation file for agents and maintainers working in this
repository. Read it first, then follow the links for the area you are changing.

## Table Of Contents

- [Project README](README.md) - concise project overview, setup, services, and
  verification commands.
- [Documentation index](docs/README.md) - map of architecture, ADR, service, and
  layer documentation.
- [Target architecture](docs/architecture/target-platform.md) - full target
  platform description and responsibility boundaries.
- [Long-term target platform](docs/architecture/long-term-target-platform.md) -
  approved post-MVP direction for surface projections, metamorphic relations,
  bounded campaigns, evidence chains, graph intelligence, and constrained LLM
  workers.
- [Patch plan to MVP](docs/architecture/patch-plan-to-mvp.md) - persistent patch
  roadmap from current state to MVP.
- [MVP gap audit](docs/architecture/mvp-gap-audit.md) - current implementation
  coverage against the MVP roadmap.
- [Current architecture sync](docs/architecture/current-state-sync.md) - current
  snapshot of implemented action-outcome memory, Surface Map runtime, Neo4j/GDS
  surface math, proposal feedback, and graph-projector operations.
- [Research operating model](docs/architecture/research-operating-model.md) -
  experience-first research substrate, memory/proposal/action lifecycle, and
  role boundaries for deterministic code, RAG, RLM, LangGraph, and CLI tools.
- [Graph math role](docs/architecture/graph-math-role.md) - Neo4j/GDS as a
  structural signal engine over typed projections, not a bug-verdict or tool
  execution layer.
- [Graph algorithm backlog](docs/architecture/graph-algorithm-backlog.md) -
  inventory and ordering gate before new graph algorithms.
- [Typed graph projections](docs/architecture/typed-graph-projections.md) -
  machine-checkable shape inventory with versioned projection contracts.
- `docs/architecture/g-http-projection-contract.md` — minimal `G_http` projection event/shape contract.
- `docs/architecture/bipartite-endpoint-param-contract.md` — minimal `G_bipartite_endpoint_param` endpoint ↔ param contract.
- [Orchestration store split plan](docs/architecture/orchestration-store-split-plan.md) -
  transaction-boundary map for splitting `OrchestrationStore` by write scenario
  instead of table wrappers.
- [Graph projector CLI boundary](docs/architecture/graph-projector-cli-boundary.md) -
  keeps `python -m graph_projector` as a thin operational entrypoint instead of
  an application hidden inside `__main__.py`.
- [Control plane](docs/architecture/control-plane.md) - action, policy,
  scheduler, event, and worker boundaries.
- [Credential reference boundary](docs/architecture/credential-ref-boundary.md) -
  leases must be issued/resolved through `CredentialLeaseService`, not directly through stores. DB-backed credential persistence must use `PostgresCredentialStore` with an explicit `SecretCodec`; wire it through `build_credential_secret_codec(...)` / `build_postgres_credential_store(...)`; use `LocalEncryptedSecretCodec` or a vault/KMS codec for non-test storage and do not add default plaintext production storage.
  future authenticated action boundary: agents see opaque refs, runners receive
  short-lived injected material only inside approved execution.
- [Agent workflow boundary](docs/architecture/agent-workflow-boundary.md) -
  LangGraph-vs-domain ownership for agent tasks, threads, proposals, and UI read models.
- [LangGraph agent worker adapter](docs/architecture/langgraph-agent-worker-adapter.md) -
  external worker path from LangGraph agent task runs back to typed domain output.
- [Refactor roadmap](docs/architecture/refactor-roadmap.md) - implementation
  order and current integration status.
- [Surface Map ADR](docs/adr/surface-map-v1.md) - surface-map bounded context
  and modeling decision.
- [Integration tests](docs/testing/integration-tests.md) - isolated external
  service test stack and safety rules.
- [Patch mascot](docs/assets/patch-animated.gif) - animated project companion
  for this branch.
- [Pixel pet assets](docs/assets/pixel-pet/README.md) - 50x50 pixel-art
  guardian animations.
- [Dashboard README](BugBountyDashBoard/README.md) - frontend application notes.
- [Surface Engine README](services/surface-engine/README.md) - deterministic
  surface canonicalization and snapshot support.

## Layer Instructions

Layer-local `AGENTS.md` files add stricter rules for specific parts of the API
codebase:

- [Application layer](src/api/application/AGENTS.md)
- [Pipeline layer](src/api/application/pipeline/AGENTS.md)
- [Infrastructure layer](src/api/infrastructure/AGENTS.md)
- [Artifact infrastructure](src/api/infrastructure/artifacts/AGENTS.md)
- [Ingestor infrastructure](src/api/infrastructure/ingestors/AGENTS.md)
- [Parser infrastructure](src/api/infrastructure/parsers/AGENTS.md)
- [Runner infrastructure](src/api/infrastructure/runners/AGENTS.md)
- [Presentation layer](src/api/presentation/AGENTS.md)

When a layer-local instruction conflicts with this index, use the stricter
instruction unless it contradicts the MVP architecture plan.

## Current Direction

Before adding new action-outcome, Surface Map, Neo4j/GDS, proposal, or
graph-projector operational layers, read
[Current architecture sync](docs/architecture/current-state-sync.md). Several
formerly planned layers are now implemented and should be extended, not rebuilt.

BugBountyMCP is moving from scan-specific endpoints toward an
experience-first research substrate:

```text
state
  -> hypothesis
  -> ActionService / policy / scope / approval / budget
  -> CommandInvocation / runner
  -> observation / artifact
  -> canonical memory in PostgreSQL
  -> OpenSearch retrieval projection
  -> Neo4j/GDS structural signal projection
  -> RAG/RLM analysis tasks
  -> LangGraph role workflow
  -> proposal / evidence / report draft
```

PostgreSQL owns canonical operational state and research memory. RabbitMQ owns
transport. OpenSearch and Neo4j are rebuildable projections. Neo4j/GDS produces
structural signals, not findings. RAG performs fast retrieval. RLM performs deep
analysis over selected context. LangGraph owns role workflow and typed proposal
output. CLI tools are effectors and must run only through ActionService.

## Hard Rules

- Do not let LLMs call RabbitMQ, shell commands, runners, or database writes
  directly.
- Do not expose tokens, cookies, API keys, Authorization headers, or session
  material to agents, proposal payloads, runner argv/stdin, logs, OpenSearch,
  Neo4j, or LangGraph state. Authenticated actions must use opaque
  `credential_refs`, `credential_secret_versions`, `credential_leases`, and the lease/injection boundary.
- Do not put raw artifacts directly into Neo4j, agent-facing OpenSearch indexes,
  or LangGraph state.
- Do not treat a hypothesis as a finding. Findings require evidence and explicit
  promotion.
- Do not treat vulnerability labels as the primary action engine. Labels such as
  IDOR, CSRF, JWT-tamper, SSRF, admin, or auth-boundary are post-hoc
  annotations, search facets, or report labels only.
- Do not treat Neo4j/GDS output as a bug verdict. Graph math produces structural
  signals that may feed hypotheses, coverage planning, RAG queries, or RLM
  analysis.
- Keep RAG and RLM separate: RAG retrieves evidence quickly; RLM performs deep
  recursive analysis over selected context. Neither executes tools.
- Do not split `OrchestrationStore` by table wrappers. Use the orchestration
  store split plan: preserve `OrchestrationStore` as a temporary facade, extract
  scenario-owned stores, and keep budget/event/outbox writes atomic.
- Keep `graph_projector.__main__` thin. CLI parser shape, command dispatch,
  runtime service builders, command handlers, and output rendering belong in the
  graph-projector CLI modules named in the CLI boundary doc. Do not copy-paste
  canonical GraphFact enqueuer builders or enqueue once/loop handlers; use the
  shared CLI enqueuer factory and batch command runners.
- Do not implement LangGraph before execution core, outbox, artifact references,
  and projection readiness are in place.
- Do not implement Neo4j GDS before GraphFact contracts, projector, rebuild, and
  safe query templates exist.
- Structural signals must use `services/graph-projector/graph_projector/structural_signal_contract.py` and `docs/architecture/structural-signal-event-model.md`; the contract validates at import time. Do not store findings, action proposals, command invocations, raw payloads, or secrets in signal events. Score/confidence range validation belongs to the future persistence contract.
- Structural-signal-derived proposals must use `services/graph-projector/graph_projector/hypothesis_from_signal_contract.py` and `docs/architecture/hypothesis-from-structural-signal-contract.md`. The contract covers only `StructuralSignal -> HypothesisProposal`; it must not create findings, action approvals, command invocations, or tool runs.
- Do not add new graph algorithms before `docs/architecture/graph-algorithm-backlog.md`
  and `docs/architecture/typed-graph-projections.md` identify the projection,
  input facts, output structural signal, lineage, and failure modes. The
  machine-checkable source is `services/graph-projector/graph_projector/projection_contracts.py`.
- Keep `research-engine` out of the core runtime. Useful research ideas should
  return later as LangGraph-node-local workflow logic.

## Verification

For Python changes, run:

```bash
python -m pytest -q
```

For graph-projector changes, also run the targeted graph/raw-artifact tests:

```bash
python -m pytest tests/infrastructure/test_graphfact_batch_store.py tests/infrastructure/test_raw_artifact_enqueue_command.py tests/infrastructure/test_graphfact_batch_apply_service.py tests/infrastructure/test_raw_artifact_graphfact_producer.py tests/infrastructure/test_graph_projection_events.py tests/infrastructure/test_neo4j_projector_upsert.py -q
```

- Authenticated tooling that requires CLI secret flags must model them as `auth_injection` metadata with bounded `allowed_cli_flags` and `allow_argv_exposure=true`; do not pass raw secrets through action options or agent payloads.
- Credential refs are stable identity handles; token/session refresh must rotate `credential_secret_versions` and update `credential_refs.current_secret_version_id`, not change proposal/action payloads. Refresh metadata is non-secret scheduling metadata only.


Credential materialization boundary:
`CredentialMaterializationPlan` is the runner-side contract for converting leased `SecretMaterial` plus `auth_injection` metadata into argv/env/request/temp-file additions. It is runner-local and secret-bearing; only audit/redacted views may leave that boundary. Env-based materialization must be passed as a `CommandInvocation` env overlay; `CommandExecutor` merges it with the inherited process environment and logs only env names.

Credential management API boundary:
Use `CredentialManagementService` / `/api/v1/credentials` for human/API registration of stable credential identities and secret rotation. Do not add endpoints that return secret values, resolve leases, or materialize runner credentials.
