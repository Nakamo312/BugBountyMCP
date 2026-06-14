# Control Plane

The control plane owns safe tool execution and durable execution state. It does
not own graph analytics, search ranking, LLM reasoning, or direct artifact body
storage.

## Responsibilities

- Accept `ToolActionRequest` objects from REST, UI, scheduler, MCP, or future
  LangGraph tools.
- Validate capability, profile, options, scope, risk, and approval state before
  creating live work.
- Persist action, policy, scope, approval, job, run, and outbox state in one
  PostgreSQL transaction.
- Publish work through the transactional outbox and RabbitMQ publisher.
- Let workers consume typed `ToolInvocation` contracts.
- Record raw artifact metadata before parsing or projection.
- Emit events that projections and agent protocols can consume idempotently.

## Boundaries

PostgreSQL is the source of truth for control-plane state. RabbitMQ is transport
only. Workers run tools and produce raw artifacts. OpenSearch and Neo4j are
rebuildable projections, not write targets for the execution core.

LLMs and LangGraph workflows may request actions only through the public Tool
Execution API. They must not publish RabbitMQ messages, claim leases, run shell
commands, call runners, or write operational state directly.

## Lifecycle

```text
request accepted
  -> capability/options validation
  -> scope/risk/approval decision
  -> action/job/run records
  -> event_outbox record
  -> RabbitMQ publish
  -> worker lease
  -> tool invocation
  -> raw artifact metadata
  -> parser/ingestor/projections
  -> result/event visibility
```

Blocked actions must leave an auditable blocked state and must not create live
jobs.

## Current Implementation Anchors

- Application contracts: `src/api/application/contracts.py`
- Action service: `src/api/application/services/action.py`
- Policy service: `src/api/application/services/policy.py`
- Scheduler: `src/api/application/scheduler.py`
- REST actions route: `src/api/presentation/rest/routes/actions.py`
- Event dispatcher: `src/api/infrastructure/events/dispatcher.py`
- Runtime manifest: `src/api/infrastructure/runtime_manifest.py`
- Tool catalog store/sync: `src/api/infrastructure/tool_catalog/`

## Required Invariants

- Options must survive DTO conversion and reach runner command builders.
- Unknown or dangerous options must be rejected before job creation.
- Out-of-scope active targets must be blocked before live work is created.
- Duplicate events and duplicate live work must be controlled by idempotency
  keys or work keys.
- Every artifact-derived projection must keep lineage back to the source
  artifact, run, parser, or producer.
