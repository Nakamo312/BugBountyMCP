from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
SPLIT_PLAN = ROOT / "docs/architecture/orchestration-store-split-plan.md"
STORE = ROOT / "src/api/infrastructure/orchestration/store.py"
RUN_CLAIM_STORE = ROOT / "src/api/infrastructure/orchestration/run_claim_store.py"
RUN_CLAIM_MODELS = ROOT / "src/api/infrastructure/orchestration/run_claim_models.py"
RUN_CLAIM_PERSISTENCE = ROOT / "src/api/infrastructure/orchestration/run_claim_persistence.py"
DISPATCH_STORE = ROOT / "src/api/infrastructure/orchestration/dispatch_store.py"
SCHEDULED_WORK_STORE = ROOT / "src/api/infrastructure/orchestration/scheduled_work_store.py"
ACTION_COMMAND_STORE = ROOT / "src/api/infrastructure/orchestration/action_command_store.py"
APPROVAL_STORE = ROOT / "src/api/infrastructure/orchestration/approval_store.py"
CAMPAIGN_STATE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_state_store.py"
EVENT_STORE = ROOT / "src/api/infrastructure/orchestration/event_store.py"
ACTION_READ_STORE = ROOT / "src/api/infrastructure/orchestration/action_read_store.py"
RUN_STATE_STORE = ROOT / "src/api/infrastructure/orchestration/run_state_store.py"
PIPELINE_CONTEXT = ROOT / "src/api/application/pipeline/context.py"
RAW_ARTIFACT_CAPTURE = ROOT / "src/api/application/pipeline/raw_artifact_capture.py"
RUN_COMPLETION_REPORTER = ROOT / "src/api/application/pipeline/run_completion_reporter.py"
SCOPE_PORT = ROOT / "src/api/application/ports/scope.py"
ARTIFACT_PORTS = ROOT / "src/api/application/ports/artifacts.py"
CONTEXT_FACTORY = ROOT / "src/api/application/pipeline/context_factory.py"
ACTION_WRITE_HELPERS = ROOT / "src/api/infrastructure/orchestration/action_write_helpers.py"
AGENTS = ROOT / "AGENTS.md"
DOCS_INDEX = ROOT / "docs/README.md"
HANDOFF = ROOT / "HANDOFF_FOR_NEW_CHAT.md"
README = ROOT / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_orchestration_store_split_plan_exists_and_names_the_problem() -> None:
    text = _read(SPLIT_PLAN)
    store_source = _read(STORE)
    run_claim_source = _read(RUN_CLAIM_STORE)
    dispatch_source = _read(DISPATCH_STORE)
    scheduled_source = _read(SCHEDULED_WORK_STORE)
    action_source = _read(ACTION_COMMAND_STORE)
    approval_source = _read(APPROVAL_STORE)
    campaign_source = _read(CAMPAIGN_STATE_STORE)
    event_source = _read(EVENT_STORE)
    action_read_source = _read(ACTION_READ_STORE)
    run_state_source = _read(RUN_STATE_STORE)

    assert "transaction-script cluster" in text
    assert "hidden transactional coupling" in text
    assert "The issue is not simply line count" in text
    assert "class OrchestrationStore" in store_source
    assert "async def claim_node_run" in store_source
    assert "self.run_claims.claim_node_run" in store_source
    assert "class RunClaimStore" in run_claim_source
    assert "async def claim_node_run" in run_claim_source
    assert "class DispatchStore" in dispatch_source
    assert "async def claim_dispatches" in dispatch_source
    assert "class ScheduledWorkStore" in scheduled_source
    assert "async def requeue_retryable_node_runs" in scheduled_source
    assert "class ActionCommandStore" in action_source
    assert "async def create_allowed_action" in action_source
    assert "class ApprovalStore" in approval_source
    assert "async def reject_action" in approval_source
    assert "class CampaignStateStore" in campaign_source
    assert "async def reconcile_campaign_lifecycle" in campaign_source
    assert "class EventStore" in event_source
    assert "async def record_event" in event_source
    assert "class ActionReadStore" in action_read_source
    assert "async def list_action_events" in action_read_source
    assert "class RunStateStore" in run_state_source
    assert "async def mark_run_finished" in run_state_source


def test_split_plan_uses_scenario_stores_not_table_wrappers() -> None:
    text = _read(SPLIT_PLAN)

    for store_name in (
        "ActionCommandStore",
        "ApprovalStore",
        "RunClaimStore",
        "CampaignStateStore",
        "ScheduledWorkStore",
        "DispatchStore",
        "EventStore",
        "ActionReadStore",
    ):
        assert store_name in text

    assert "Do not split by table name" in text
    assert "Do not add a new layer over it" in text
    assert "compatibility facade" in text
    assert "five smaller combiners" in text


def test_run_claim_store_is_the_first_extraction_target() -> None:
    text = _read(SPLIT_PLAN)
    flat = _flat(text)

    assert "Extract `RunClaimStore` first" in text
    assert "claim-key idempotency" in text
    assert "work-key active-run fallback after insert races" in text
    assert "coalesced trigger append" in text
    assert "Budget operations must remain atomic with the run insert" in text
    assert "0043_extract_run_claim_store" in text
    assert "existing claim? depth blocked? retryable failed work reusable? cooldown blocked? reserve campaign budget? insert run" in flat


def test_characterization_requirements_cover_claim_retry_budget_and_dispatch() -> None:
    text = _read(SPLIT_PLAN)

    required_contracts = (
        "duplicate `claim_key` returns the existing claim",
        "max depth blocks before any transaction writes",
        "retryable failed `work_key` returns existing work",
        "cooldown blocks before budget lock",
        "campaign budget block updates refilled tokens",
        "successful scheduled claim inserts a run",
        "insert-race fallback re-reads by claim key",
        "active work fallback appends a coalesced trigger",
        "coalesced trigger append is a bounded tail sample",
        "dispatch leasing locks only eligible pending/failed/expired rows",
        "failed dispatch increments attempts",
        "retry requeue only requeues policies",
        "exhausted retry runs move to `dead`",
    )
    for contract in required_contracts:
        assert contract in text


def test_query_boundary_rule_allows_named_reviewable_sql_boundaries() -> None:
    text = _read(SPLIT_PLAN)

    assert "Complex PostgreSQL-specific JSONB" in text
    assert "named helpers or query objects" in text
    assert "Raw SQL is not banned" in text
    assert "short, parameterized, localized, and covered by tests" in text


def test_navigation_links_orchestration_split_plan() -> None:
    for path in (AGENTS, DOCS_INDEX, README, HANDOFF):
        text = _read(path)
        assert "orchestration-store-split-plan.md" in text


def test_run_claim_store_extraction_moves_claim_helpers_out_of_facade() -> None:
    store_source = _read(STORE)
    run_claim_source = _read(RUN_CLAIM_STORE)
    models_source = _read(RUN_CLAIM_MODELS)
    persistence_source = _read(RUN_CLAIM_PERSISTENCE)

    for helper in (
        "select_node_run_claim",
        "select_active_work_claim",
        "select_retryable_failed_work_claim",
        "append_coalesced_trigger",
    ):
        assert helper not in store_source
        assert helper in persistence_source

    assert "def refilled_tokens" in models_source
    assert "self.run_claims = RunClaimStore(session_factory)" in store_source
    assert "return await self.run_claims.claim_node_run" in store_source


def test_run_claim_store_flow_refactor_uses_typed_internal_values() -> None:
    store_source = _read(STORE)
    run_claim_source = _read(RUN_CLAIM_STORE)
    models_source = _read(RUN_CLAIM_MODELS)

    for type_name in (
        "class RunClaimRequest",
        "class ExistingWorkClaim",
        "class CampaignBudgetSnapshot",
        "class CampaignBudgetReservation",
    ):
        assert type_name in models_source

    for phase in (
        "async def _try_reuse_retryable_work",
        "async def _check_cooldown_block",
        "async def _reserve_campaign_budget_if_needed",
        "async def _insert_claimed_run",
        "async def _recover_from_insert_race",
    ):
        assert phase in run_claim_source

    assert "locals().copy()" not in run_claim_source
    assert "return await self._claim_node_run(" in run_claim_source
    assert "RunClaimRequest(" in run_claim_source
    assert "existing_triggers" not in run_claim_source
    assert "append_coalesced_trigger_statement" not in store_source


def test_split_plan_records_run_claim_flow_refactor_before_dispatch_split() -> None:
    text = _read(SPLIT_PLAN)
    patch_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(tuple("123456."))]

    assert any("0044_refactor_run_claim_store_flow" in line for line in patch_lines)
    assert any("0045_extract_dispatch_and_scheduled_work_stores" in line for line in patch_lines)
    assert not any("0044_extract_dispatch" in line for line in patch_lines)
    assert not any("0044_extract_scheduled_work" in line for line in patch_lines)
    assert "Patch 0044 keeps that boundary and cleans the extracted flow itself" in text
    assert "ExistingWorkClaim" in text
    assert "CampaignBudgetSnapshot" in text
    assert "CampaignBudgetReservation" in text


def test_dispatch_and_scheduled_work_extraction_moves_helpers_out_of_facade() -> None:
    store_source = _read(STORE)
    dispatch_source = _read(DISPATCH_STORE)
    scheduled_source = _read(SCHEDULED_WORK_STORE)

    assert "self.dispatches = DispatchStore(session_factory, self.settings)" in store_source
    assert "self.scheduled_work = ScheduledWorkStore(session_factory)" in store_source
    assert "return await self.dispatches.claim_dispatches" in store_source
    assert "return await self.dispatches.mark_sent" in store_source
    assert "return await self.dispatches.mark_failed" in store_source
    assert "return await self.scheduled_work.lease_ready_scheduled_node_runs" in store_source
    assert "return await self.scheduled_work.requeue_retryable_node_runs" in store_source

    for moved_body_marker in (
        "with_for_update(skip_locked=True, of=event_dispatches)",
        "QueueConfig.get_routing_key",
        "pg_notify",
    ):
        assert moved_body_marker not in store_source
        assert moved_body_marker in dispatch_source

    for moved_body_marker in (
        "with_for_update(skip_locked=True, of=runs)",
        "random.uniform",
        "Marked failed: stale scheduled active run exceeded timeout",
        "retry_reason=retry_policy.terminal_outcomes[0]",
    ):
        assert moved_body_marker not in store_source
        assert moved_body_marker in scheduled_source



def test_dispatch_and_scheduled_work_stores_are_not_extracted_god_methods() -> None:
    dispatch_source = _read(DISPATCH_STORE)
    scheduled_source = _read(SCHEDULED_WORK_STORE)

    for phase in (
        "async def _select_claimable_dispatch_rows",
        "async def _mark_dispatch_rows_locked",
        "def _dispatch_record_from_row",
    ):
        assert phase in dispatch_source

    for phase in (
        "async def _select_ready_scheduled_rows",
        "async def _mark_rows_leased",
        "async def _select_retryable_run_ids",
        "async def _requeue_run_ids",
        "async def _select_exhausted_retry_run_ids",
        "async def _mark_exhausted_runs_dead",
        "class _RetryPolicy",
    ):
        assert phase in scheduled_source

    assert "async def claim_dispatches" in dispatch_source
    assert "async def lease_ready_scheduled_node_runs" in scheduled_source
    assert "async def requeue_retryable_node_runs" in scheduled_source

def test_split_plan_records_dispatch_and_scheduled_extraction_before_action_split() -> None:
    text = _read(SPLIT_PLAN)
    patch_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(tuple("123456."))
    ]

    assert any("0045_extract_dispatch_and_scheduled_work_stores" in line for line in patch_lines)
    assert any("0046_extract_action_approval_campaign_stores" in line for line in patch_lines)
    assert "Patch 0045 extracts `DispatchStore` and `ScheduledWorkStore`" in text
    assert "OrchestrationStore` keeps compatibility facade methods" in text


def test_action_approval_campaign_extraction_moves_write_scenarios_out_of_facade() -> None:
    store_source = _read(STORE)
    action_source = _read(ACTION_COMMAND_STORE)
    approval_source = _read(APPROVAL_STORE)
    campaign_source = _read(CAMPAIGN_STATE_STORE)
    event_source = _read(EVENT_STORE)

    assert "self.action_commands = ActionCommandStore(" in store_source
    assert "self.approvals = ApprovalStore(" in store_source
    assert "self.campaigns = CampaignStateStore(" in store_source
    assert "self.events = EventStore(session_factory)" in store_source
    assert "return await self.action_commands.record_policy_result" in store_source
    assert "await self.action_commands.create_allowed_action" in store_source
    assert "return await self.approvals.approve_and_create_queued_job" in store_source
    assert "return await self.approvals.reject_action" in store_source
    assert "return await self.campaigns.get_campaign_activity" in store_source
    assert "await self.events.record_event" in store_source

    for moved_marker in (
        "async def record_policy_result",
        "async def create_allowed_action",
        "async def create_queued_job",
    ):
        assert moved_marker in action_source

    for moved_marker in (
        "async def get_action_for_approval",
        "async def approve_and_create_queued_job",
        "async def reject_action",
        "async def record_approval_decision",
    ):
        assert moved_marker in approval_source

    for moved_marker in (
        "async def get_campaign_activity",
        "async def reconcile_active_campaigns",
        "async def mark_campaign_terminal",
        "async def upsert_campaign",
    ):
        assert moved_marker in campaign_source

    assert "async def record_event" in event_source
    assert "insert_event_store_row" in event_source


def test_scheduled_work_store_boundary_and_deferred_smells_are_recorded() -> None:
    text = _read(SPLIT_PLAN)
    scheduled_source = _read(SCHEDULED_WORK_STORE)

    assert "must not grow reconciliation, campaign budget, run accounting, or event emission" in text
    assert "old concurrency model: select retryable ids, then update by id" in _flat(text)
    assert "FOR UPDATE SKIP LOCKED" in text
    assert "one by one" in text
    assert "Boundary rule: this store must stay limited to scheduled work queue" in scheduled_source
    assert "campaign budget" in scheduled_source
    assert "event emission" in scheduled_source


def test_patch_order_records_action_approval_campaign_extraction() -> None:
    text = _read(SPLIT_PLAN)

    assert "0046_extract_action_approval_campaign_stores" in text
    assert "ActionCommandStore" in text
    assert "ApprovalStore" in text
    assert "CampaignStateStore" in text
    assert "EventStore" in text
    assert "direct behavior tests for `DispatchStore` and `ScheduledWorkStore`" in text
    assert "0047_extract_action_read_and_run_state_stores" in text


def test_action_read_and_run_state_extraction_moves_remaining_facade_bodies() -> None:
    store_source = _read(STORE)
    action_read_source = _read(ACTION_READ_STORE)
    run_state_source = _read(RUN_STATE_STORE)

    assert "self.action_reads = ActionReadStore(session_factory)" in store_source
    assert "self.run_states = RunStateStore(session_factory)" in store_source
    assert "return await self.action_reads.list_actions" in store_source
    assert "return await self.action_reads.list_action_events" in store_source
    assert "return await self.run_states.mark_run_started" in store_source
    assert "return await self.run_states.mark_run_finished" in store_source
    assert "await self.run_states.mark_run_needs_reconcile" in store_source

    for moved_marker in (
        "event_store.c.payload",
        "raw_artifacts.join",
        "ActionRequest.model_validate",
        "ActionArtifactReference(",
    ):
        assert moved_marker not in store_source
        assert moved_marker in action_read_source

    for moved_marker in (
        "scanner_started_at",
        "flushing_at",
        "Invalid terminal run status",
        "needs_reconcile=True",
    ):
        assert moved_marker not in store_source
        assert moved_marker in run_state_source


def test_approval_request_helper_is_neutral_write_helper_not_approval_store_leak() -> None:
    action_source = _read(ACTION_COMMAND_STORE)
    approval_source = _read(APPROVAL_STORE)
    helper_source = _read(ACTION_WRITE_HELPERS)

    assert "from api.infrastructure.orchestration.approval_store import" not in action_source
    assert "record_approval_request_if_needed" in helper_source
    assert "async def record_approval_request_if_needed" not in approval_source


def test_event_store_only_swallows_duplicate_event_integrity_errors() -> None:
    event_source = _read(EVENT_STORE)

    assert "def is_duplicate_event_integrity_error" in event_source
    assert "except IntegrityError as exc" in event_source
    assert "if not is_duplicate_event_integrity_error(exc):" in event_source
    assert "raise" in event_source


def test_patch_order_records_action_read_and_run_state_extraction() -> None:
    text = _read(SPLIT_PLAN)

    assert "0047_extract_action_read_and_run_state_stores" in text
    assert "ActionReadStore" in text
    assert "RunStateStore" in text
    assert "approval request creation helper" in text
    assert "duplicate event id" in text


def test_action_write_stores_accept_resolved_commands_without_persisting_command_internals() -> None:
    action_source = _read(ACTION_COMMAND_STORE)
    helper_source = _read(ACTION_WRITE_HELPERS)
    approval_source = _read(APPROVAL_STORE)
    campaign_source = _read(CAMPAIGN_STATE_STORE)

    assert "action: ResolvedActionCommand" in action_source
    assert "action: ResolvedActionCommand" in helper_source
    assert "action: ResolvedActionCommand" in approval_source
    assert "action: ResolvedActionCommand" in campaign_source
    assert "action: ActionRequest" not in action_source
    assert "action: ActionRequest" not in helper_source
    assert "action: ActionRequest" not in approval_source
    assert "action: ActionRequest" not in campaign_source
    assert "action_request_payload(action)" in action_source
    assert "Persist the public request shape" in helper_source


def test_orchestration_store_is_deprecated_compatibility_facade_only() -> None:
    store_source = _read(STORE)

    assert "deprecated_compatibility_facade = True" in store_source
    assert "DeprecationWarning" not in store_source
    assert "Adding methods here keeps the old one-object-knows-everything model alive" in store_source


def test_pipeline_context_delegates_raw_capture_run_completion_and_scope_filtering() -> None:
    context_source = _read(PIPELINE_CONTEXT)
    raw_capture_source = _read(RAW_ARTIFACT_CAPTURE)
    run_completion_source = _read(RUN_COMPLETION_REPORTER)
    artifact_ports_source = _read(ARTIFACT_PORTS)
    scope_port_source = _read(SCOPE_PORT)
    context_factory_source = _read(CONTEXT_FACTORY)

    assert "class RawArtifactCapture" in raw_capture_source
    assert "RawOutputCapturePort" in raw_capture_source
    assert "RawArtifactMetadataWriter" in raw_capture_source
    assert "FileRawOutputStore" not in raw_capture_source
    assert "RawArtifactRepository" not in raw_capture_source

    assert "class RunCompletionReporter" in run_completion_source
    assert "PipelineRunStatePort" in run_completion_source
    assert "ActionOutcomeRecorder" in run_completion_source
    assert "AsyncContainer" not in run_completion_source
    assert "request_container" not in run_completion_source

    assert "class RawOutputCapturePort" in artifact_ports_source
    assert "class RawArtifactMetadataWriter" in artifact_ports_source
    assert "ProcessEvent" in artifact_ports_source
    assert "infrastructure.schemas.models.process_event" not in artifact_ports_source
    assert "class ScopeFilterPort" in scope_port_source
    assert "PipelineContextFactory" in context_factory_source
    assert "scope_filter" in context_factory_source
    assert "RawArtifactCapture(" in context_source
    assert "RunCompletionReporter(" in context_source
    assert "ProgramUnitOfWork" not in context_source
    assert "requires_bound_job_id_for_recording" in context_source
    assert "FileRawOutputStore" not in context_source
    assert "RawArtifactRepository" not in context_source
    assert "Cannot durably emit pipeline event without bound job_id" in context_source
    assert "execution_facade_only = True" in context_source


def test_patch_order_records_facade_deprecation_and_context_split() -> None:
    text = _read(SPLIT_PLAN)

    assert "0048_orchestration_facade_deprecation_and_context_split" in text
    assert "deprecated compatibility facade" in text
    assert "ResolvedActionCommand" in text
    assert "RawArtifactCapture" in text
    assert "RunCompletionReporter" in text


def test_pipeline_boundary_guardrails_are_documented() -> None:
    text = _read(SPLIT_PLAN)

    assert "0049_pipeline_boundary_guardrails" in text
    assert "must not gain new side effects" in text
    assert "temporary migration aliases" in text
    assert "legacy-only fallback" in text
