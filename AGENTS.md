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
- [Patch plan to MVP](docs/architecture/patch-plan-to-mvp.md) - persistent patch
  roadmap from current state to MVP.
- [MVP gap audit](docs/architecture/mvp-gap-audit.md) - current implementation
  coverage against the MVP roadmap.
- [Control plane](docs/architecture/control-plane.md) - action, policy,
  scheduler, event, and worker boundaries.
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

BugBountyMCP is moving from scan-specific endpoints toward a controlled
execution platform:

```text
ToolActionRequest
  -> policy/scope/approval
  -> transactional outbox
  -> RabbitMQ
  -> worker
  -> raw artifact
  -> parser/processor/ingestor
  -> PostgreSQL canonical facts
  -> OpenSearch projection
  -> Neo4j GraphFacts
  -> LangGraph wait/resume
  -> hypothesis/evidence/report draft
```

PostgreSQL owns canonical operational state. RabbitMQ owns transport. OpenSearch
and Neo4j are rebuildable read models. LangGraph owns agent-human workflow, not
tool execution.

## Hard Rules

- Do not let LLMs call RabbitMQ, shell commands, runners, or database writes
  directly.
- Do not put raw artifacts directly into Neo4j, agent-facing OpenSearch indexes,
  or LangGraph state.
- Do not treat a hypothesis as a finding. Findings require evidence and explicit
  promotion.
- Do not implement LangGraph before execution core, outbox, artifact references,
  and projection readiness are in place.
- Do not implement Neo4j GDS before GraphFact contracts, projector, rebuild, and
  safe query templates exist.
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
