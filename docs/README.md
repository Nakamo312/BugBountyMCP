# BugBountyMCP Documentation

This directory contains architecture, roadmap, and decision records for the
BugBountyMCP platform.

## Start Here

- [Root agent index](../AGENTS.md) - top-level navigation and hard rules.
- [Project README](../README.md) - setup, services, and verification commands.
- [Target architecture](architecture/target-platform.md) - detailed platform
  architecture and long-term system boundaries.
- [Long-term target platform](architecture/long-term-target-platform.md) -
  approved destination after the base MVP, including surface projections,
  metamorphic relations, bounded campaigns, evidence chains, graph
  intelligence, and constrained LLM workers.
- [Patch plan to MVP](architecture/patch-plan-to-mvp.md) - persistent patch
  roadmap from the current branch to MVP.
- [MVP gap audit](architecture/mvp-gap-audit.md) - current branch status against
  the roadmap, including done/partial/missing areas.
- [Current architecture sync](architecture/current-state-sync.md) - current
  implementation snapshot for action outcome memory, Surface Map runtime,
  Neo4j/GDS surface math, proposal feedback, and graph-projector operations.
- [Research operating model](architecture/research-operating-model.md) -
  experience-first research substrate, deterministic/RAG/RLM/LangGraph/CLI role
  boundaries, and action lifecycle rules.
- [Graph projector CLI boundary](architecture/graph-projector-cli-boundary.md)
- [Graph math role](architecture/graph-math-role.md) - Neo4j/GDS as structural
  signal engine over typed projections.
- [Graph algorithm backlog](architecture/graph-algorithm-backlog.md) - inventory
  and ordering contract for typed projections and future graph algorithms.
- [Typed graph projections](architecture/typed-graph-projections.md) - human
  review surface for versioned machine-checkable `ProjectionContract` shape inventory.
- [G_http Projection Contract](architecture/g-http-projection-contract.md) — minimal HTTP surface projection event/shape contract.
- [G_bipartite_endpoint_param Contract](architecture/bipartite-endpoint-param-contract.md) — minimal endpoint ↔ parameter bipartite contract.
- [Orchestration store split plan](architecture/orchestration-store-split-plan.md) -
  safe extraction map and characterization requirements for the oversized
  orchestration write store.
- [Credential reference boundary](architecture/credential-ref-boundary.md) -
  approved boundary for future authenticated scans without exposing tokens to
  agents, logs, read models, or runner argv/stdin.

## Project Mascot

Patch is the project companion for this branch: a small cybernetic axolotl-like
mascot for tests, patches, graph projection, and integration work.

- [Static Patch](assets/patch.png)
- [Animated Patch](assets/patch-animated.gif)
- [Pixel Pet Assets](assets/pixel-pet/README.md)

## Architecture

- [Current architecture sync](architecture/current-state-sync.md) - current
  implementation snapshot after the action-outcome, Surface Map, Neo4j/GDS,
  proposal, and graph-projector operational patches.
- [Research operating model](architecture/research-operating-model.md) -
  baseline for the experience-first project direction and role boundaries.
- [Graph projector CLI boundary](architecture/graph-projector-cli-boundary.md)
- [Graph math role](architecture/graph-math-role.md) - baseline for typed graph
  projections and structural signal semantics.
- [Graph algorithm backlog](architecture/graph-algorithm-backlog.md) - typed
  projection inventory, missing algorithms, and implementation order.
- [Typed graph projections](architecture/typed-graph-projections.md) - required
  versioned projection contracts before new GDS/Cypher logic.
- [Orchestration store split plan](architecture/orchestration-store-split-plan.md) -
  transaction-boundary map for splitting `OrchestrationStore` without changing
  claim, retry, budget, approval, dispatch, or campaign semantics.
- [Control plane](architecture/control-plane.md) - action request lifecycle,
  policy, scheduler, workers, event boundaries, and graph/search projection
  responsibilities.
- [Refactor roadmap](architecture/refactor-roadmap.md) - practical order for
  integrating the architecture into the current repository.
- [Target platform](architecture/target-platform.md) - full target architecture,
  including execution, data, search, graph, agent workflow, safety, and
  dashboard planes.
- [Long-term target platform](architecture/long-term-target-platform.md) -
  normative post-MVP architecture. Its implementation snapshot is historical;
  use the MVP gap audit for current branch status.
- [Patch plan to MVP](architecture/patch-plan-to-mvp.md) - patch-by-patch MVP
  plan. This is the source of truth for implementation order.
- [MVP gap audit](architecture/mvp-gap-audit.md) - working checklist for
  current implementation coverage and remaining gaps.

## Decisions

- [Surface Map V1 ADR](adr/surface-map-v1.md) - explains the Surface Map bounded
  context and why raw bodies are not sent directly to LLMs or promoted directly
  to findings.
- [Transactional outbox ADR](adr/event-store-dispatches-outbox.md) - accepts
  `event_store` plus `event_dispatches` as the MVP outbox and defines at-least-
  once delivery and consumer idempotency requirements.

## Testing

- [Integration tests](testing/integration-tests.md) - isolated Docker stack,
  safety rules, and integration pytest workflow.

## Service And Layer Docs

- [Dashboard README](../BugBountyDashBoard/README.md)
- [Surface Engine README](../services/surface-engine/README.md)
- [Application layer instructions](../src/api/application/AGENTS.md)
- [Pipeline layer instructions](../src/api/application/pipeline/AGENTS.md)
- [Infrastructure layer instructions](../src/api/infrastructure/AGENTS.md)
- [Presentation layer instructions](../src/api/presentation/AGENTS.md)

## Documentation Rules

- Keep this index and the root `AGENTS.md` updated when adding major docs.
- Keep the patch roadmap stable; do not renumber roadmap patches casually.
- Prefer links to existing docs over duplicating long architecture text.
- Document responsibility boundaries before adding new services or workflow
  runtimes.

- `architecture/structural-signal-event-model.md` — contract-only durable event/read-model boundary for structural signals.
- [Hypothesis from structural signal](architecture/hypothesis-from-structural-signal-contract.md) — contract-only `StructuralSignal -> HypothesisProposal` boundary.
