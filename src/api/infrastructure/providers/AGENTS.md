# Infrastructure Provider Instructions

This package owns DI/composition wiring that constructs concrete repositories,
stores, runners, gateways, event buses, and runtime adapters for application
ports and services.

## Rules

- Add new provider wiring here, not under `api.application.providers`.
- The old `api.application.providers.*` alias package has been removed; do not reintroduce it.
- Prefer returning application ports/contracts when a concrete infrastructure
  adapter is consumed by application services.
