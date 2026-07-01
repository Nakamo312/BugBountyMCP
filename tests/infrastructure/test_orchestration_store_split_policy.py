from __future__ import annotations
from pathlib import Path
ROOT = Path(".")
SPLIT_PLAN = ROOT / "docs/architecture/orchestration-store-split-plan.md"
STORE = ROOT / "src/api/infrastructure/orchestration/store.py"
RUN_CLAIM_STORE = ROOT / "src/api/infrastructure/orchestration/run_claim_store.py"
RUN_CLAIM_MODELS = ROOT / "src/api/infrastructure/orchestration/run_claim_models.py"
PIPELINE_CONTRACTS = ROOT / "src/api/application/pipeline_contracts.py"
RUN_CLAIM_PERSISTENCE = ROOT / "src/api/infrastructure/orchestration/run_claim_persistence.py"
RUN_CLAIM_TRANSACTION = ROOT / "src/api/infrastructure/orchestration/run_claim_transaction.py"
RUN_CLAIM_BUDGET = ROOT / "src/api/infrastructure/orchestration/run_claim_budget.py"
RUN_CLAIM_WORK_REUSE = ROOT / "src/api/infrastructure/orchestration/run_claim_work_reuse.py"
DISPATCH_LEASING = ROOT / "src/api/infrastructure/orchestration/dispatch_leasing.py"
DISPATCH_WRITER = ROOT / "src/api/infrastructure/orchestration/dispatch_writer.py"
SCHEDULED_WORK_STORE = ROOT / "src/api/infrastructure/orchestration/scheduled_work_store.py"
SCHEDULED_LEASING = ROOT / "src/api/infrastructure/orchestration/scheduled_leasing.py"
SCHEDULED_RECOVERY = ROOT / "src/api/infrastructure/orchestration/scheduled_recovery.py"
SCHEDULED_RETRY = ROOT / "src/api/infrastructure/orchestration/scheduled_retry.py"
ACTION_POLICY_RESULT_STORE = ROOT / "src/api/infrastructure/orchestration/action_policy_result_store.py"
ALLOWED_ACTION_QUEUE_STORE = ROOT / "src/api/infrastructure/orchestration/allowed_action_queue_store.py"
ACTION_COMMAND_TRANSACTIONS = ROOT / "src/api/infrastructure/orchestration/action_command_transactions.py"
APPROVAL_REQUEST_STORE = ROOT / "src/api/infrastructure/orchestration/approval_request_store.py"
APPROVAL_DECISION_STORE = ROOT / "src/api/infrastructure/orchestration/approval_decision_store.py"
APPROVAL_TRANSACTIONS = ROOT / "src/api/infrastructure/orchestration/approval_transactions.py"
CAMPAIGN_ACTIVITY = ROOT / "src/api/infrastructure/orchestration/campaign_activity.py"
CAMPAIGN_LIFECYCLE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_lifecycle_store.py"
CAMPAIGN_WRITE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_write_store.py"
EVENT_STORE = ROOT / "src/api/infrastructure/orchestration/event_store.py"
ACTION_READ_STORE = ROOT / "src/api/infrastructure/orchestration/action_read_store.py"
ACTION_READ_QUERIES = ROOT / "src/api/infrastructure/orchestration/action_read_queries.py"
ACTION_READ_MAPPERS = ROOT / "src/api/infrastructure/orchestration/action_read_mappers.py"
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
    run_claim_source = _read(RUN_CLAIM_STORE)
    lease_source = _read(DISPATCH_LEASING)
    writer_source = _read(DISPATCH_WRITER)
    scheduled_source = ""
    policy_result_source = _read(ACTION_POLICY_RESULT_STORE)
    allowed_queue_source = _read(ALLOWED_ACTION_QUEUE_STORE)
    approval_request_source = _read(APPROVAL_REQUEST_STORE)
    approval_decision_source = _read(APPROVAL_DECISION_STORE)
    campaign_lifecycle_source = _read(CAMPAIGN_LIFECYCLE_STORE)
    campaign_write_source = _read(CAMPAIGN_WRITE_STORE)
    event_source = _read(EVENT_STORE)
    action_read_source = _read(ACTION_READ_STORE)
    run_state_source = _read(RUN_STATE_STORE)
    assert "transaction-script cluster" in text
    assert "hidden transactional coupling" in text
    assert "The issue is not simply line count" in text
    assert not STORE.exists()
    assert "class RunClaimStore" in run_claim_source
    assert "async def claim_node_run" in run_claim_source
    assert "class DispatchLeaseStore" in lease_source
    assert "async def claim_dispatches" in lease_source
    assert "class DispatchWriterStore" in writer_source
    assert "async def enqueue_dispatch" in writer_source
    assert not SCHEDULED_WORK_STORE.exists()
    assert "class ScheduledLeaseStore" in _read(SCHEDULED_LEASING)
    assert "class ScheduledRecoveryStore" in _read(SCHEDULED_RECOVERY)
    assert "class ScheduledRetryStore" in _read(SCHEDULED_RETRY)
    assert "class ActionPolicyResultStore" in policy_result_source
    assert "async def record_policy_result" in policy_result_source
    assert "class AllowedActionQueueStore" in allowed_queue_source
    assert "async def create_allowed_action" in allowed_queue_source
    assert "class ApprovalRequestStore" in approval_request_source
    assert "async def get_action_for_approval" in approval_request_source
    assert "class ApprovalDecisionStore" in approval_decision_source
    assert "async def reject_action" in approval_decision_source
    assert "class CampaignLifecycleStore" in campaign_lifecycle_source
    assert "async def reconcile_campaign_lifecycle" in campaign_lifecycle_source
    assert "class CampaignWriteStore" in campaign_write_source
    assert "class EventStore" in event_source
    assert "async def record_event" in event_source
    assert "class ActionReadStore" in action_read_source
    assert "async def list_action_events" in action_read_source
    assert "class RunStateStore" in run_state_source
    assert "async def mark_run_finished" in run_state_source
def test_split_plan_uses_scenario_stores_not_table_wrappers() -> None:
    text = _read(SPLIT_PLAN)
    for store_name in (
        "ActionPolicyResultStore",
        "AllowedActionQueueStore",
        "ApprovalRequestStore",
        "ApprovalDecisionStore",
        "RunClaimStore",
        "CampaignWriteStore",
        "DispatchWriterStore",
        "DispatchLeaseStore",
        "EventStore",
        "ActionReadStore",
    ):
        assert store_name in text
    assert (
        "ScheduledWorkStore" in text
        or all(
            store_name in text
            for store_name in (
                "ScheduledLeaseStore",
                "ScheduledRecoveryStore",
                "ScheduledRetryStore",
            )
        )
    )
    assert "Do not split by table name" in text
    assert "Do not add a new layer over it" in text
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
def test_run_claim_store_extraction_keeps_claim_helpers_in_scenario_modules() -> None:
    assert not STORE.exists()
    run_claim_source = _read(RUN_CLAIM_STORE)
    transaction_source = _read(RUN_CLAIM_TRANSACTION)
    models_source = _read(RUN_CLAIM_MODELS)
    persistence_source = _read(RUN_CLAIM_PERSISTENCE)
    for helper in (
        "select_node_run_claim",
        "select_active_work_claim",
        "select_retryable_failed_work_claim",
        "append_coalesced_trigger",
    ):
        assert helper in persistence_source
    assert "def refilled_tokens" in models_source
def test_run_claim_store_flow_refactor_uses_typed_internal_values() -> None:
    assert not STORE.exists()
    run_claim_source = _read(RUN_CLAIM_STORE)
    transaction_source = _read(RUN_CLAIM_TRANSACTION)
    models_source = _read(RUN_CLAIM_MODELS)
    pipeline_contracts_source = _read(PIPELINE_CONTRACTS)
    assert "class NodeRunClaimRequest" in pipeline_contracts_source
    for type_name in (
        "class ExistingWorkClaim",
        "class CampaignBudgetSnapshot",
        "class CampaignBudgetReservation",
    ):
        assert type_name in models_source
    for phase in (
        "async def claim_node_run_in_session",
        "def depth_limit_exceeded",
        "async def reserve_budget_or_block",
    ):
        assert phase in transaction_source
        assert phase not in run_claim_source
    assert "locals().copy()" not in run_claim_source
    assert "locals().copy()" not in transaction_source
    assert "async def _claim_node_run" not in run_claim_source
    assert "NodeRunClaimRequest(" not in run_claim_source
    assert "def claim_node_run(self, request: NodeRunClaimRequest)" in run_claim_source
    assert "claim_node_run_in_session(session" in run_claim_source
    assert "existing_triggers" not in transaction_source
def test_run_claim_store_policy_and_reuse_bodies_are_split_out() -> None:
    run_claim_source = _read(RUN_CLAIM_STORE)
    transaction_source = _read(RUN_CLAIM_TRANSACTION)
    budget_source = _read(RUN_CLAIM_BUDGET)
    reuse_source = _read(RUN_CLAIM_WORK_REUSE)
    for marker in (
        "def reserve_campaign_budget_if_needed",
        "snapshot.block_reason(",
        "CampaignBudgetReservation(",
        "tokens_available=snapshot.tokens_available",
    ):
        assert marker in budget_source
        assert marker not in run_claim_source
        assert marker not in transaction_source
    for marker in (
        "def try_reuse_retryable_work",
        "def check_cooldown_block",
        "def recover_from_insert_race",
        "await session.rollback()",
        "raise insert_error",
        "timedelta(seconds=float(request.cooldown_seconds))",
    ):
        assert marker in reuse_source
        assert marker not in run_claim_source
        assert marker not in transaction_source
    for marker in (
        "await try_reuse_retryable_work",
        "await check_cooldown_block",
        "await recover_from_insert_race",
    ):
        assert marker in transaction_source
        assert marker not in run_claim_source
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
def test_dispatch_and_scheduled_work_extraction_keeps_helpers_in_scenario_modules() -> None:
    assert not STORE.exists()
    lease_source = _read(DISPATCH_LEASING)
    writer_source = _read(DISPATCH_WRITER)
    scheduled_source = ""
    leasing_source = _read(SCHEDULED_LEASING)
    recovery_source = _read(SCHEDULED_RECOVERY)
    retry_source = _read(SCHEDULED_RETRY)
    for moved_body_marker in (
        "with_for_update(skip_locked=True, of=event_dispatches)",
        "QueueConfig.get_routing_key",
        "pg_notify",
    ):
        assert (moved_body_marker in lease_source or moved_body_marker in writer_source)
    for moved_body_marker, target_source in (
        ("with_for_update(skip_locked=True, of=runs)", leasing_source),
        ("random.uniform", retry_source),
        ("Marked failed: stale scheduled active run exceeded timeout", recovery_source),
        ("retry_reason=retry_policy.terminal_outcomes[0]", retry_source),
    ):
        assert moved_body_marker not in scheduled_source
        assert moved_body_marker in target_source
def test_dispatch_and_scheduled_work_stores_are_not_extracted_god_methods() -> None:
    lease_source = _read(DISPATCH_LEASING)
    writer_source = _read(DISPATCH_WRITER)
    scheduled_source = ""
    leasing_source = _read(SCHEDULED_LEASING)
    recovery_source = _read(SCHEDULED_RECOVERY)
    retry_source = _read(SCHEDULED_RETRY)
    for phase in (
        "async def select_claimable_dispatch_rows",
        "async def mark_dispatch_rows_locked",
        "def dispatch_record_from_row",
    ):
        assert phase in lease_source
    assert "class ScheduledLeaseStore" in leasing_source
    assert "async def lease_ready_scheduled_node_runs" in leasing_source
    assert "async def select_ready_scheduled_rows" in leasing_source
    assert "async def mark_rows_leased" in leasing_source
    assert "class ScheduledRecoveryStore" in recovery_source
    assert "async def recover_stale_leases" in recovery_source
    assert "async def fail_stale_scheduled_active_runs" in recovery_source
    assert "class ScheduledRetryStore" in retry_source
    assert "async def requeue_retryable_node_runs" in retry_source
    assert "async def select_retryable_run_ids" in retry_source
    assert "async def requeue_run_ids" in retry_source
    assert "async def select_exhausted_retry_run_ids" in retry_source
    assert "async def mark_exhausted_runs_dead" in retry_source
    assert "class RetryPolicy" in retry_source
    assert "ScheduledLeaseStore(session_factory)" not in scheduled_source
    assert "ScheduledRecoveryStore(session_factory)" not in scheduled_source
    assert "ScheduledRetryStore(session_factory)" not in scheduled_source
    assert "async def claim_dispatches" in lease_source
def test_split_plan_records_dispatch_and_scheduled_extraction_before_action_split() -> None:
    text = _read(SPLIT_PLAN)
    patch_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(tuple("123456."))
    ]
    assert any("0045_extract_dispatch_and_scheduled_work_stores" in line for line in patch_lines)
    assert any("0046_extract_action_approval_campaign_stores" in line for line in patch_lines)
    assert (
        "Patch 0045 extracts `DispatchWriterStore`/`DispatchLeaseStore` and `ScheduledWorkStore`" in text
        or "Patch 0045 extracts `DispatchWriterStore`/`DispatchLeaseStore` and the first scheduled queue boundary" in text
    )
def test_action_approval_campaign_extraction_keeps_write_scenarios_in_scenario_modules() -> None:
    assert not STORE.exists()
    policy_result_source = _read(ACTION_POLICY_RESULT_STORE)
    allowed_queue_source = _read(ALLOWED_ACTION_QUEUE_STORE)
    action_tx_source = _read(ACTION_COMMAND_TRANSACTIONS)
    approval_request_source = _read(APPROVAL_REQUEST_STORE)
    approval_decision_source = _read(APPROVAL_DECISION_STORE)
    approval_tx_source = _read(APPROVAL_TRANSACTIONS)
    campaign_lifecycle_source = _read(CAMPAIGN_LIFECYCLE_STORE)
    campaign_write_source = _read(CAMPAIGN_WRITE_STORE)
    event_source = _read(EVENT_STORE)

    assert "async def record_policy_result" in policy_result_source
    assert "async def create_allowed_action" in allowed_queue_source
    assert "async def record_policy_result_in_session" in action_tx_source
    assert "async def create_allowed_action_in_session" in action_tx_source
    assert "async def create_queued_job_in_session" not in action_tx_source
    assert "async def get_action_for_approval" in approval_request_source
    assert "async def get_scope_id" in approval_request_source
    assert "async def approve_and_create_queued_job" in approval_decision_source
    assert "async def reject_action" in approval_decision_source
    for moved_marker in (
        "async def select_action_for_approval",
        "async def approve_and_create_queued_job_in_session",
        "async def reject_action_in_session",
        "async def record_approval_decision",
        "async def select_latest_scope_id",
    ):
        assert moved_marker in approval_tx_source
    for moved_marker in (
        "async def get_campaign_activity",
        "async def reconcile_active_campaigns",
        "async def mark_campaign_terminal",
    ):
        assert moved_marker in campaign_lifecycle_source
    for moved_marker in (
        "async def upsert_campaign",
        "async def activate_campaign",
    ):
        assert moved_marker in campaign_write_source
    assert "async def record_event" in event_source
    assert "insert_event_store_row" in event_source

def test_scheduled_work_store_boundary_and_deferred_smells_are_recorded() -> None:
    text = _read(SPLIT_PLAN)
    scheduled_source = ""
    assert (
        "must not grow reconciliation, campaign budget, run accounting, or event emission" in text
        or (
            "must not grow reconciliation, campaign budget, run" in text
            and "accounting, or event emission" in text
        )
    )
    assert "old concurrency model: select retryable ids, then update by id" in _flat(text)
    assert "FOR UPDATE SKIP LOCKED" in _flat(text)
    assert "one by one" in text
    assert "class ScheduledLeaseStore" in _read(SCHEDULED_LEASING)
    assert "class ScheduledRecoveryStore" in _read(SCHEDULED_RECOVERY)
    assert "class ScheduledRetryStore" in _read(SCHEDULED_RETRY)
def test_patch_order_records_action_approval_campaign_extraction() -> None:
    text = _read(SPLIT_PLAN)
    assert "0046_extract_action_approval_campaign_stores" in text
    assert "ActionPolicyResultStore" in text
    assert "AllowedActionQueueStore" in text
    assert "ApprovalRequestStore" in text
    assert "ApprovalDecisionStore" in text
    assert "CampaignWriteStore" in text or "CampaignLifecycleStore" in text
    assert "EventStore" in text
    assert (
        "direct behavior tests for `DispatchWriterStore`, `DispatchLeaseStore`," in text
        and "`ScheduledLeaseStore`, `ScheduledRecoveryStore`, and `ScheduledRetryStore`" in text
    )
    assert "0047_extract_action_read_and_run_state_stores" in text
def test_action_read_and_run_state_extraction_keeps_read_and_run_state_bodies_split() -> None:
    assert not STORE.exists()
    action_read_source = _read(ACTION_READ_STORE)
    action_read_query_source = _read(ACTION_READ_QUERIES)
    action_read_mapper_source = _read(ACTION_READ_MAPPERS)
    run_state_source = _read(RUN_STATE_STORE)
    assert "async def list_action_events" in action_read_source
    for moved_marker in (
        "event_store.c.payload",
        "raw_artifacts.join",
    ):
        assert moved_marker in action_read_query_source
    for moved_marker in (
        "ActionRequest.model_validate",
        "ActionArtifactReference(",
    ):
        assert moved_marker in action_read_mapper_source
    for moved_marker in (
        "scanner_started_at",
        "flushing_at",
        "Invalid terminal run status",
        "needs_reconcile=True",
    ):
        assert moved_marker in run_state_source
def test_approval_request_helper_is_neutral_write_helper_not_approval_store_leak() -> None:
    action_tx_source = _read(ACTION_COMMAND_TRANSACTIONS)
    approval_request_source = _read(APPROVAL_REQUEST_STORE)
    helper_source = _read(ACTION_WRITE_HELPERS)
    assert "from api.infrastructure.orchestration.approval_store import" not in action_tx_source
    assert "record_approval_request_if_needed" in helper_source
    assert "async def record_approval_request_if_needed" not in approval_request_source

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
    policy_result_source = _read(ACTION_POLICY_RESULT_STORE)
    allowed_queue_source = _read(ALLOWED_ACTION_QUEUE_STORE)
    action_tx_source = _read(ACTION_COMMAND_TRANSACTIONS)
    helper_source = _read(ACTION_WRITE_HELPERS)
    approval_decision_source = _read(APPROVAL_DECISION_STORE)
    approval_tx_source = _read(APPROVAL_TRANSACTIONS)
    campaign_write_source = _read(CAMPAIGN_WRITE_STORE)
    for source in (
        policy_result_source,
        allowed_queue_source,
        action_tx_source,
        helper_source,
        approval_decision_source,
        approval_tx_source,
        campaign_write_source,
    ):
        assert "action: ResolvedActionCommand" in source
        assert "action: ActionRequest" not in source
    assert "action_request_payload(action)" in action_tx_source
    assert "Persist the public request shape" in helper_source
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
    assert "ResolvedActionCommand" in text
    assert "RawArtifactCapture" in text
    assert "RunCompletionReporter" in text
def test_pipeline_boundary_guardrails_are_documented() -> None:
    text = _read(SPLIT_PLAN)
    assert "0049_pipeline_boundary_guardrails" in text
    assert "must not gain new side effects" in text
    assert "are gone, not new stable APIs" in text
    assert "api.infrastructure.schemas.models.process_event" in text
    assert "legacy-only fallback" in text
