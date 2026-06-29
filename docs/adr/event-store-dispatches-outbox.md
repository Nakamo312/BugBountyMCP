# ADR: EventStore and EventDispatches as the MVP transactional outbox

Date: 2026-06-24

Status: accepted

## Decision

For the MVP, the combination of `event_store` and `event_dispatches` is the
transactional outbox:

- `event_store` owns the immutable event envelope;
- `event_dispatches` owns destination-specific delivery state;
- action, policy, scope, job, run, event, and pending delivery are committed in
  one PostgreSQL transaction;
- `EventDispatcher` claims deliveries with `FOR UPDATE SKIP LOCKED`, publishes
  the stored envelope, and records success or retry state.

Separate literal `event_outbox` and `event_inbox` tables are not required for
the MVP. Adding aliases or duplicate tables would create two competing delivery
models without changing the reliability boundary.

## Delivery semantics

Delivery is at least once, not exactly once.

A dispatcher lease prevents concurrent workers from normally claiming the same
delivery. A process or network failure after broker publication but before the
database success update can still cause a later retry. Therefore:

- `event_id` is the stable idempotency key;
- consumers must handle duplicate delivery safely;
- one event and destination have at most one `event_dispatches` row through
  `uq_event_dispatches_event_destination`;
- retry attempts preserve the original `event_store` envelope.

## Failure behavior

- A database rollback leaves no queued action delivery.
- RabbitMQ failure leaves a retryable or dead delivery row.
- Expired dispatcher leases can be reclaimed.
- PostgreSQL notification wakes the dispatcher, while periodic sweeping remains
  the recovery path.

## Consequences

- Roadmap references to `event_outbox` mean this semantic boundary, not a
  mandatory table name.
- `event_inbox` remains unnecessary for ordinary workers while their existing
  work keys and idempotent state transitions provide duplicate protection.
- Agent delivery uses its own durable `agent_inbox` because it has separate
  acknowledgement and workflow semantics.
- Live PostgreSQL and RabbitMQ integration tests remain required before the
  controlled execution loop can be declared complete.

