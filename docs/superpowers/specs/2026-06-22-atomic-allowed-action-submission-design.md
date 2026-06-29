# Atomic Allowed Action Submission Design

## Goal

Persist an immediately allowed action and its policy, scope, job, initial run,
event-store row, and RabbitMQ dispatch row in one PostgreSQL transaction.

## Design

`ActionService.request_action` continues to persist blocked and
approval-required decisions without creating live work. For an allowed
decision it builds the `EventEnvelope` first and calls one orchestration-store
operation. That operation writes the campaign, action request, policy/scope
details, job, run, event-store row, and `event_dispatches` outbox row through
one session and one commit.

The existing approval transition remains unchanged because it already writes
its approval decision, job, run, event, and outbox atomically.

## Failure Semantics

Any exception before the combined operation commits leaves none of the allowed
action's rows committed. RabbitMQ publication remains asynchronous: after the
database commit, the pending `event_dispatches` row is the durable publication
source.

## Testing

- An application regression test requires `ActionService` to use the combined
  store operation for allowed actions.
- A store contract test requires the combined operation to contain all writes
  and a single commit.
- The full Python test suite verifies existing blocked, approval, API, and
  dispatcher behavior.
