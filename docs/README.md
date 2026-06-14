# BugBountyMCP Documentation

This directory contains architecture, roadmap, and decision records for the
BugBountyMCP platform.

## Start Here

- [Root agent index](../AGENTS.md) - top-level navigation and hard rules.
- [Project README](../README.md) - setup, services, and verification commands.
- [Target architecture](architecture/target-platform.md) - detailed platform
  architecture and long-term system boundaries.
- [Patch plan to MVP](architecture/patch-plan-to-mvp.md) - persistent patch
  roadmap from the current branch to MVP.
- [MVP gap audit](architecture/mvp-gap-audit.md) - current branch status against
  the roadmap, including done/partial/missing areas.

## Project Mascot

Patch is the project companion for this branch: a small cybernetic axolotl-like
mascot for tests, patches, graph projection, and integration work.

- [Static Patch](assets/patch.png)
- [Animated Patch](assets/patch-animated.gif)
- [Pixel Pet Assets](assets/pixel-pet/README.md)

## Architecture

- [Control plane](architecture/control-plane.md) - action request lifecycle,
  policy, scheduler, workers, event boundaries, and graph/search projection
  responsibilities.
- [Refactor roadmap](architecture/refactor-roadmap.md) - practical order for
  integrating the architecture into the current repository.
- [Target platform](architecture/target-platform.md) - full target architecture,
  including execution, data, search, graph, agent workflow, safety, and
  dashboard planes.
- [Patch plan to MVP](architecture/patch-plan-to-mvp.md) - patch-by-patch MVP
  plan. This is the source of truth for implementation order.
- [MVP gap audit](architecture/mvp-gap-audit.md) - working checklist for
  current implementation coverage and remaining gaps.

## Decisions

- [Surface Map V1 ADR](adr/surface-map-v1.md) - explains the Surface Map bounded
  context and why raw bodies are not sent directly to LLMs or promoted directly
  to findings.

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
