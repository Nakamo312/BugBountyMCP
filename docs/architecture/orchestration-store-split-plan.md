# Orchestration Store Split Plan

Patch 0042 records the split target for `src/api/infrastructure/orchestration/store.py`
before moving code. The current `OrchestrationStore` is still the production
entry point, but it has become a transaction-script cluster rather than a single
store. The next patches must cut responsibility by write scenario, not by table.

This is a safety patch. It adds characterization tests and a split map so the
first extraction does not change claiming, retry, dispatch, approval, or campaign
budget semantics by accident.

## Current Problem

`OrchestrationStore` owns too many transactional domains:

- campaign lifecycle and activity accounting;
- campaign budget locking, refill, blocking, and consumption;
- action request creation and action detail rows;
- approval request and approval decision persistence;
- event store writes and outbox dispatch enqueueing;
- dispatch leasing, success, failure, and retry state;
- node run claiming, claim-key idempotency, work-key deduplication, cooldowns,
  retryable failed work, and trigger coalescing;
- scheduled run leasing and stale-run recovery;
- terminal run transitions, retry values, requeueing, and dead-lettering;
- action read models for events, runs, and artifacts.

That means a change in run claiming can alter budget consumption, retry reuse,
coalesced trigger samples, campaign status, job status, or deduplication. A
store with this shape cannot be reviewed by bounded context.

The issue is not simply line count. The issue is hidden transactional coupling.
Moving methods into smaller files without changing the ownership model would
only create five smaller combiners.

## Split Rule

Split by durable write scenario and invariant:

```text
request -> policy/approval -> command/job -> run claim/scheduling
        -> runner state -> event store/outbox -> campaign accounting
```

Do not split by table name. A table may belong to multiple transaction surfaces,
but a write method must have one primary owner.

`OrchestrationStore` was only an extraction scaffold. Do not reintroduce a compatibility facade over the split stores; application services must depend on narrower scenario interfaces directly. Do not add a new layer over it.

## Target Stores

### Action write stores

`ActionPolicyResultStore` owns terminal or approval-required policy result recording.

`AllowedActionQueueStore` owns the allowed-action queue path and its outbox write in the same caller transaction.

They must not lease scheduled work, claim node runs, retry failed runs, or expose approval state transitions.

### Approval stores

`ApprovalRequestStore` owns approval request reads and scope lookup for approval workflows.

`ApprovalDecisionStore` owns approval decisions, action status transitions from `requires_approval`, and approval-time queue creation.

They must not expose action submission writes or node-run claiming.

### RunClaimStore

Owns node-run creation and deduplication:

- `claim_node_run`;
- claim-key idempotency;
- max expansion depth block;
- retryable failed work reuse;
- work-key active-run fallback after insert races;
- cooldown blocks;
- coalesced trigger append;
- run insert;
- job status update required by a new scheduled run.

It may call a campaign budget collaborator inside the same database transaction,
but it must not own campaign lifecycle reconciliation.

### Campaign lifecycle and write stores

Campaign behavior is not one store anymore:

- `campaign_activity.py` owns campaign activity query construction and mapping;
- `CampaignLifecycleStore` owns lifecycle reads/reconciliation and terminal transitions;
- `CampaignWriteStore` owns only caller-transaction campaign upsert/activation primitives used by action command and approval flows;
- campaign budget reservation stays with the run-claim transaction boundary, not with lifecycle reconciliation.

Campaign upsert/activation must remain atomic with the action/job/run/outbox transaction that calls it.
Budget operations must remain atomic with the run insert that consumes them.
Campaign lifecycle reconciliation must not gain action command writes or budget accounting.

### Scheduled queue stores

Already-created scheduled work queue lifecycle is split across three ports:

- `ScheduledLeaseStore` owns active scheduled run counts and ready-run leasing;
- `ScheduledRecoveryStore` owns stale lease recovery and stale active-run failure;
- `ScheduledRetryStore` owns retry requeue and exhausted retry transition to `dead`.

There is no `ScheduledWorkStore` combiner. It was useful during extraction, then
removed once `NodeRegistry` could depend on lease, recovery, and retry ports
separately. None of these stores may decide whether a new run should exist. That
remains `RunClaimStore`. They must not grow reconciliation, campaign budget, run
accounting, or event emission scenarios. Those would recreate the next
mini-combiner.

Known deferred smell: `ScheduledRetryStore.requeue_retryable_node_runs` still
preserves the old concurrency model: select retryable ids, then update by id.
That means two retry workers can race toward the same failed run. Future
behavior-changing cleanup should use a locked selection such as `FOR UPDATE SKIP
LOCKED` or a single guarded `UPDATE ... RETURNING` boundary before changing retry
semantics.

Known deferred scaling issue: `requeue_run_ids` still updates rows one by one.
That keeps the old semantics and supports per-row jitter, but bulk update should
be considered when jitter is disabled and retry batches become large.

### DispatchWriterStore and DispatchLeaseStore

Own outbox write and delivery state without a dispatch combiner:

- `DispatchWriterStore` creates event dispatch rows inside the caller's transaction;
- `DispatchWriterStore` emits PostgreSQL notify for dispatch wake-up;
- `DispatchLeaseStore` owns `claim_dispatches`;
- `DispatchLeaseStore` owns successful dispatch marking;
- `DispatchLeaseStore` owns failed dispatch retry/dead state.

They do not build hypotheses, claim node runs, or mutate campaign budget.

### EventStore

Owns durable event persistence:

- `record_event`;
- run placeholder creation for legacy event envelopes during the migration;
- event store row insertion;
- event-to-outbox enqueue through `DispatchWriterStore` or a session-bound outbox
  helper;
- event read helpers needed by action read models.

Event persistence and outbox enqueue must stay in one transaction.

### ActionReadStore

Owns read-only action views:

- `list_actions`;
- `get_action`;
- `list_action_events`;
- `list_action_runs`;
- `list_action_artifacts`.

This store should not share write helpers with command creation.

## First Extraction Target

Extract `RunClaimStore` first. It is the highest-risk cluster because it mixes:

- candidate selection;
- claim-key idempotency;
- depth limits;
- retry reuse;
- cooldown checks;
- campaign budget refill/block/consume;
- run insert;
- job/campaign state updates;
- active-work fallback after insert races;
- coalesced trigger append.

The extracted method should read like a scenario, not a query dump:

```text
existing claim?
depth blocked?
retryable failed work reusable?
cooldown blocked?
reserve campaign budget?
insert run
consume budget and update job/campaign state
commit
on insert race: return existing claim or coalesce into active work
```

A first extraction may keep SQLAlchemy Core statements, but each statement must
have a name tied to the invariant it protects. Complex PostgreSQL-specific
statements are allowed only behind a small function with tests.

## Characterization Tests Required Before Moving Code

The behavior below must stay covered before and after extraction:

- duplicate `claim_key` returns the existing claim and does not lock campaign
  budget;
- max depth blocks before any transaction writes;
- retryable failed `work_key` returns existing work and does not consume budget;
- cooldown blocks before budget lock;
- campaign budget block updates refilled tokens but does not insert a run;
- successful scheduled claim inserts a run, consumes runs/targets/tokens, and
  updates job/campaign state atomically;
- insert-race fallback re-reads by claim key before work-key fallback;
- active work fallback appends a coalesced trigger and commits the append;
- coalesced trigger append is a bounded tail sample, not an unbounded JSONB log;
- dispatch leasing locks only eligible pending/failed/expired rows;
- failed dispatch increments attempts and either schedules retry or marks dead;
- retry requeue only requeues policies with `max_attempts > 1` and matching
  terminal outcomes;
- exhausted retry runs move to `dead` and do not requeue forever.

Patch 0042 adds only tests and the split map. Patch 0043 performs the first code
movement by extracting `RunClaimStore` behind the existing `OrchestrationStore`
facade.

## Query Boundary Rule

SQLAlchemy Core is acceptable for simple insert/update/select statements.
Complex PostgreSQL-specific JSONB, ordinality, lock, or coalescing operations
must live behind named helpers or query objects. Raw SQL is not banned when it is
short, parameterized, localized, and covered by tests. The real rule is that the
application layer must not see SQL details and the invariant must be reviewable.

## Patch Order

1. `0042_orchestration_store_split_plan_and_characterization_tests` — this
   document plus characterization tests; no production code movement.
2. `0043_extract_run_claim_store` — delegate `claim_node_run` through a new
   `RunClaimStore` while keeping the external `OrchestrationStore` API stable.
   Completed: `RunClaimStore` owns claim-key idempotency, retryable failed work
   reuse, cooldown checks, campaign budget lock/refill/block/consume, run insert,
   insert-race fallback, and coalesced trigger append.
3. `0044_refactor_run_claim_store_flow` — keep the same behavior but turn the
   extracted claim method into a workflow over named phases and typed internal
   values: precheck, retry reuse, cooldown, budget reservation, run insert,
   campaign/job mutation, and insert-race recovery.
4. `0045_extract_dispatch_and_scheduled_work_stores` — split event dispatch
   leasing/retry/dead state from already-created scheduled work leasing/requeue.
   Completed: `DispatchWriterStore` owns outbox enqueue and notify;
   `DispatchLeaseStore` owns dispatch claim leasing, sent transition, and
   failed/dead transition. The scheduled queue first moved into `ScheduledWorkStore`, then P19 removed
   that combiner and left `ScheduledLeaseStore`, `ScheduledRecoveryStore`, and
   `ScheduledRetryStore` as separate ports.
5. `0046_extract_action_approval_campaign_stores` — split action command
   creation, approval state, campaign lifecycle/accounting, event persistence,
   and keep action read models on the facade until the write boundaries settle.
   P23 later replaces the broad `CampaignStateStore` with `CampaignLifecycleStore`
   plus `CampaignWriteStore` so lifecycle reconciliation and action-time campaign
   writes no longer share one object.
   Also add direct behavior tests for `DispatchWriterStore`, `DispatchLeaseStore`,
   `ScheduledLeaseStore`, `ScheduledRecoveryStore`, and `ScheduledRetryStore` so facade/source-grep
   tests are not the only regression guard.
6. `0047_extract_action_read_and_run_state_stores` — split action read models into
   `ActionReadStore` and runner state transitions into `RunStateStore`, keeping
   old `OrchestrationStore` methods as compatibility facades. Also move the
   approval request creation helper to a neutral session-bound write helper and
   narrow `EventStore.record_event` idempotency to duplicate event id conflicts.
7. `0048_orchestration_facade_deprecation_and_context_split` — mark
   `OrchestrationStore` as a deprecated compatibility facade, make action write
   stores consume `ResolvedActionCommand` explicitly, keep persisted request JSON
   in the public `ActionRequest` shape, and split raw artifact capture/run-state
   reporting out of `PipelineContext`.
8. `0049_pipeline_boundary_guardrails` — no new behavior; document
   `PipelineContext` as an execution facade that must not gain new side effects,
   mark temporary compatibility imports, and make the `ScanNode` no-factory path
   explicit legacy fallback.
9. `P19_remove_scheduled_work_combiner` — delete the temporary
   `ScheduledWorkStore` shell and inject scheduled lease, recovery, and retry
   ports separately into `NodeRegistry`.
10. Return to graph backlog and typed projection contracts once orchestration
   write boundaries are small enough to review.

The next patch should not add LangGraph behavior, new scanner chains, credential
runtime materialization, or graph algorithms. It should only continue shrinking
the orchestration transaction surfaces while preserving characterization tests.

## After RunClaimStore Extraction

`RunClaimStore` is now the owner of node-run creation and deduplication.
`OrchestrationStore.claim_node_run(...)` remains only a compatibility facade so
application services do not change during the extraction. New claim-related
helpers must go into `run_claim_store.py`, not back into `store.py`.

Patch 0044 keeps that boundary and cleans the extracted flow itself. The public
method packs arguments into `RunClaimRequest`; the internal flow works through
`ExistingWorkClaim`, `CampaignBudgetSnapshot`, and `CampaignBudgetReservation`
instead of spreading raw row mappings through the whole scenario.

Patch 0045 extracts `DispatchWriterStore`/`DispatchLeaseStore` and the first scheduled queue boundary.
Dispatch write, leasing, retry, and dead-state transitions no longer live in a
combined facade. P19 removes the temporary `ScheduledWorkStore` combiner and
uses `ScheduledLeaseStore`, `ScheduledRecoveryStore`, and `ScheduledRetryStore`
directly from pipeline runtime wiring.

Patch 0046 extracts action/approval write stores, the original `CampaignStateStore`,
and `EventStore`. P23 removes that broad campaign object: `CampaignLifecycleStore`
owns lifecycle reads/reconciliation, while `CampaignWriteStore` owns only
action-time campaign upsert/activation primitives. P25 removes the broad
`ActionCommandStore`/`ApprovalStore` implementations and keeps four concrete
scenario stores: `ActionPolicyResultStore`, `AllowedActionQueueStore`,
`ApprovalRequestStore`, and `ApprovalDecisionStore`. Event persistence and outbox
enqueue stay atomic because action flows call the execution writer and dispatch
writer inside one transaction and commit once.

Patch 0047 extracts `ActionReadStore` and `RunStateStore`. Action read queries
and runner state transitions no longer live in the facade. The patch also fixes
two extraction smells from 0046: approval request creation moved into neutral
session-bound write helpers instead of an approval store side effect, and
`EventStore.record_event` now treats only duplicate event id conflicts as
idempotent instead of swallowing every `IntegrityError`.

After P15, `OrchestrationStore` no longer exists. Do not add a new all-in-one
orchestration facade. Return to graph backlog and typed projection contracts
unless a concrete regression appears in the split stores.

Patch 0048 keeps `OrchestrationStore` only as a deprecated compatibility facade.
New callers should request scenario-owned ports/stores directly. Action write
stores now advertise `ResolvedActionCommand` at the command boundary while
serializing the stored `request` column back to the public `ActionRequest` shape
so approval lookup does not reconstruct a request from resolved-command internals.

`PipelineContext` no longer constructs `FileRawOutputStore` or talks directly to
`PipelineRunStatePort`. Raw stream capture lives in `RawArtifactCapture`; terminal run transitions and action-outcome recording live in `RunCompletionReporter`. Durable event
emission also refuses to invent a job id when an event recorder is attached; the
job identity must come from the bound upstream run.


Patch 0049 does not introduce a new orchestration split. It records guardrails
from review: `PipelineContext` remains an execution facade and must not gain new
side effects; new persistence/storage/scheduling/outcome behavior must enter via
explicit ports or terminal hooks wired by `PipelineContextFactory`.
`RunCompletionReporter` may keep the current terminal transition plus
action-outcome-memory hook while it stays small, but outcome-memory branching
should move to a separate terminal hook before it grows. The compatibility import
removed provider alias paths such as `api.application.providers.pipeline` and
`api.application.pipeline.run_state_reporter`, and
`api.infrastructure.schemas.models.process_event` are gone, not new stable APIs. Direct `ScanNode` construction without a context factory is a
legacy-only fallback and intentionally has no raw-capture, run-state, outcome, or
scope-filter ports.
