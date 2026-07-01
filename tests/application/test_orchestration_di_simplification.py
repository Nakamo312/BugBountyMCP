from pathlib import Path


ACTION_RUNTIME_PROVIDER = Path("src/api/infrastructure/providers/action_runtime.py")
RESEARCH_RUNTIME_PROVIDER = Path("src/api/infrastructure/providers/research_runtime.py")
PIPELINE_STORE = Path("src/api/infrastructure/orchestration/pipeline_store.py")
SCHEDULED_WORK_STORE = Path("src/api/infrastructure/orchestration/scheduled_work_store.py")


def test_action_runtime_provider_uses_scenario_stores_not_orchestration_facades() -> None:
    source = ACTION_RUNTIME_PROVIDER.read_text(encoding="utf-8")

    assert "api.infrastructure.orchestration.store" not in source
    assert "api.infrastructure.orchestration.pipeline_store" not in source
    assert "def get_orchestration_store" not in source
    assert "def get_pipeline_orchestration_store_port" not in source
    assert not PIPELINE_STORE.exists()
    for store_name in (
        "ActionPolicyResultStore",
        "AllowedActionQueueStore",
        "ActionReadStore",
        "ApprovalRequestStore",
        "ApprovalDecisionStore",
        "CampaignWriteStore",
        "DispatchWriterStore",
        "DispatchLeaseStore",
        "EventStore",
        "RunClaimStore",
        "RunStateStore",
        "ScheduledLeaseStore",
        "ScheduledRecoveryStore",
        "ScheduledRetryStore",
    ):
        assert store_name in source
    assert "NodeRunClaimPort" in source
    assert "ScheduledLeasePort" in source
    assert "ScheduledRecoveryPort" in source
    assert "ScheduledRetryPort" in source
    assert not SCHEDULED_WORK_STORE.exists()
    assert "PipelineRunStatePort" in source


def test_research_runtime_provider_uses_campaign_lifecycle_store_for_lifecycle() -> None:
    source = RESEARCH_RUNTIME_PROVIDER.read_text(encoding="utf-8")

    assert "api.infrastructure.orchestration.store" not in source
    assert "CampaignLifecycleStore" in source
    assert "def get_campaign_lifecycle_reader" in source
    assert "def get_campaign_lifecycle_reconciler" in source
