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

Keep `OrchestrationStore` as a compatibility facade during the extraction. Do not add a new layer over it. The facade should delegate to smaller stores and be
removed only after application services depend on the narrower interfaces.

## Target Stores

### ActionCommandStore

Owns the action-to-command write path:

- `create_allowed_action`;
- action request row;
- target/options rows;
- scope decision row;
- policy decision row;
- job row;
- initial run row for inline command execution when that remains part of action
  creation;
- campaign creation/activation only through a small campaign collaborator.

It must not lease scheduled work, claim node runs, retry failed runs, or dispatch
outbox rows.

### ApprovalStore

Owns human/policy approval state:

- approval request creation;
- approval decision recording;
- action rejection;
- action status transition from `requires_approval` to rejected/allowed when the
  approval flow explicitly owns the transition.

It must not create jobs, claim runs, or touch campaign budget.

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

### CampaignStateStore

Owns campaign accounting and lifecycle:

- `_campaign_activity_query` and activity mapping;
- `get_campaign_activity`;
- `reconcile_campaign_lifecycle`;
- `reconcile_active_campaigns`;
- `_persist_campaign_lifecycle`;
- `mark_campaign_terminal`;
- budget lock/refill/check/consume operations used by `RunClaimStore`;
- campaign creation/activation primitives used by `ActionCommandStore`.

Budget operations must remain atomic with the run insert that consumes them.
That means `RunClaimStore` must receive a session-bound collaborator, not call a
separate transaction.

### ScheduledWorkStore

Owns already-created scheduled work queue lifecycle:

- `count_scheduled_active_runs_by_node`;
- `lease_ready_scheduled_node_runs`;
- `recover_stale_leases`;
- `fail_stale_scheduled_active_runs`;
- `requeue_retryable_node_runs`;
- exhausted retry transition to `dead`.

It does not decide whether a new run should exist. That is `RunClaimStore`. It
must not grow reconciliation, campaign budget, run accounting, or event emission
scenarios. Those would turn it into the next mini-combiner.

Known deferred smell: `requeue_retryable_node_runs` still preserves the old
concurrency model: select retryable ids, then update by id. That means two retry
workers can race toward the same failed run. Future behavior-changing cleanup
should use a locked selection such as `FOR UPDATE SKIP LOCKED` or a single guarded
`UPDATE ... RETURNING` boundary before changing retry semantics.

Known deferred scaling issue: `_requeue_run_ids` still updates rows one by one.
That keeps the old semantics and supports per-row jitter, but bulk update should
be considered when jitter is disabled and retry batches become large.

### DispatchStore

Owns outbox delivery state:

- event dispatch row creation;
- PostgreSQL notify for dispatch wake-up;
- `claim_dispatches`;
- successful dispatch marking;
- failed dispatch retry/dead state.

It does not build hypotheses, claim node runs, or mutate campaign budget.

### EventStore

Owns durable event persistence:

- `record_event`;
- run placeholder creation for legacy event envelopes during the migration;
- event store row insertion;
- event-to-outbox enqueue through `DispatchStore` or a session-bound outbox
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
   Completed: `DispatchStore` owns outbox enqueue, notify statement, dispatch
   claim leasing, sent transition, and failed/dead transition.
   `ScheduledWorkStore` owns active scheduled run counts, ready-run leasing,
   stale lease recovery, stale active-run failure, retry requeue, and exhausted
   retry transition to dead. `OrchestrationStore` keeps compatibility facade
   methods only.
5. `0046_extract_action_approval_campaign_stores` — split action command
   creation, approval state, campaign lifecycle/accounting, event persistence,
   and keep action read models on the facade until the write boundaries settle.
   Also add direct behavior tests for `DispatchStore` and `ScheduledWorkStore`
   so facade/source-grep tests are not the only regression guard.
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
9. Return to graph backlog and typed projection contracts once orchestration
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

Patch 0045 extracts `DispatchStore` and `ScheduledWorkStore`. Dispatch
leasing/retry/dead state and scheduled run leasing/requeue no longer live in the
facade. `OrchestrationStore` keeps compatibility facade methods so application
services do not change during the extraction.

Patch 0046 extracts `ActionCommandStore`, `ApprovalStore`, `CampaignStateStore`,
and `EventStore`. Event persistence and outbox enqueue stay atomic because action
flows use the shared session-bound `insert_job_run_and_dispatch(...)` helper and
commit once. `OrchestrationStore` still owns action read models and runner state
transitions as compatibility surface.

Patch 0047 extracts `ActionReadStore` and `RunStateStore`. Action read queries
and runner state transitions no longer live in the facade. The patch also fixes
two extraction smells from 0046: approval request creation helper moved out of
`approval_store.py` into neutral session-bound write helpers, and
`EventStore.record_event` now treats only duplicate event id conflicts as
idempotent instead of swallowing every `IntegrityError`.

After 0047, `OrchestrationStore` is expected to remain a compatibility facade
with legacy static helpers only. Do not add new orchestration scenarios to it.
Return to graph backlog and typed projection contracts unless a concrete
regression appears in the split stores.

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
paths `api.application.providers.pipeline`,
`api.infrastructure.schemas.models.process_event`, and
`api.application.pipeline.run_state_reporter` are temporary migration aliases, not
new stable APIs. Direct `ScanNode` construction without a context factory is a
legacy-only fallback and intentionally has no raw-capture, run-state, outcome, or
scope-filter ports.
