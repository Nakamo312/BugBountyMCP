# Application Layer Instructions

This layer owns control-plane use cases and typed contracts. Keep it mostly
independent from infrastructure details.

Read first when changing this layer:

- [Control plane](../../../docs/architecture/control-plane.md)
- [Refactor roadmap](../../../docs/architecture/refactor-roadmap.md)

## Rules

- Use application contracts from `contracts.py` for actions, policy decisions,
  event envelopes, scan profiles, and tool results.
- New scan execution paths must go through `ActionService` and `PolicyService`.
- Do not import concrete runner, ingestor, database, repository, parser, or
  provider implementations from application services. Infrastructure wiring
  belongs under `api.infrastructure.*`; `api.application.providers.*` is only
  a deprecated compatibility alias package.
- `tests/application/test_application_import_boundary.py` is the AST boundary gate.
  New `api.application` -> `api.infrastructure` imports must not be added; shrink
  its temporary allowlist when compatibility aliases or legacy seams are removed.
- Do not add LLM execution authority here. LLM output should become typed
  advisory intent, not direct scanner execution.
- Prefer narrow services that preserve rollback paths over broad orchestration
  facades.

## Scheduler

- Scheduler config is declarative YAML.
- Scheduler may create action requests only through `ActionService`.
- Do not make scheduler publish events or run tools directly.
- Treat current scheduler state as in-memory only.

## Experience Ranking

- Action outcome memory may feed internal planners, schedulers, and workflow
  proposal workers. It should not be surfaced as ad-hoc REST handlers or public
  ranking APIs.
- Graph/GDS similarity belongs behind application or worker boundaries. It may
  produce typed advisory intent, proposed actions, or scheduler inputs, but it
  must not bypass `ActionService`, policy, scope, approval, or budget checks.

## Agent Task Threads

- Human prompts become `agent_tasks`, visible task messages, and a bounded handoff to a LangGraph-owned workflow thread. The prompt text must not become direct tool execution.
- Agent task runtime execution should happen in an internal LangGraph worker/platform adapter. Do not start a parallel long-running agent-task runtime loop inside the public FastAPI process.
- Agent replies may point to proposals, actions, artifacts, facts, or graph refs, but real tool execution still goes through `ActionService`, policy, scope, approval, and budget.
- Keep agent task runtime behind an internal worker boundary. Do not expose LangGraph/GDS/runtime execution as public REST controls, and do not duplicate LangGraph thread/checkpoint/stream semantics in application code.
- Agent runtimes must pass through the budget policy wrapper. Default to deterministic/no-model mode, trim context before runtime execution, and require explicit configuration before deep/expensive reasoning.

Event type contracts live in `api.application.event_contracts`. Do not import `EventType` from `api.infrastructure.events.event_types` in application code.

`api.application.providers.*` is a deprecated compatibility package. New code must import provider wiring from `api.infrastructure.providers.*` or from the real composition root. The AST boundary tests reject new imports of the compatibility provider package.

Event bus transport adapters live in infrastructure. Application code must depend on `api.application.ports.events.EventBusPort` and must not import `api.infrastructure.events.event_bus` or `api.infrastructure.events.queue_config`. Queue topology belongs to infrastructure provider wiring.
