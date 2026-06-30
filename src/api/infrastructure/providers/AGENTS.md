# Infrastructure Provider Instructions

This package owns DI/composition wiring that constructs concrete repositories,
stores, runners, gateways, event buses, and runtime adapters for application
ports and services.

## Rules

- Add new provider wiring here, not under `api.application.providers`.
- Keep `api.application.providers.*` modules as deprecated compatibility aliases
  only; do not add concrete imports or provider methods there.
- Prefer returning application ports/contracts when a concrete infrastructure
  adapter is consumed by application services.
