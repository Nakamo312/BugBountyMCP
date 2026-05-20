# Application Layer Instructions

This layer owns control-plane use cases and typed contracts. Keep it mostly
independent from infrastructure details.

## Rules

- Use application contracts from `contracts.py` for actions, policy decisions,
  event envelopes, scan profiles, and tool results.
- New scan execution paths must go through `ActionService` and `PolicyService`.
- Do not import concrete runner, ingestor, database, repository, or parser
  implementations from application services except in composition/catalog
  boundaries already covered by architecture tests.
- Do not add LLM execution authority here. LLM output should become typed
  advisory intent, not direct scanner execution.
- Prefer narrow services that preserve rollback paths over broad orchestration
  facades.

## Scheduler

- Scheduler config is declarative YAML.
- Scheduler may create action requests only through `ActionService`.
- Do not make scheduler publish events or run tools directly.
- Treat current scheduler state as in-memory only.
