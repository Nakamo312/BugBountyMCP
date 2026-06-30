from pathlib import Path


ACTION_RUNTIME_PROVIDER = Path("src/api/infrastructure/providers/action_runtime.py")
RESEARCH_RUNTIME_PROVIDER = Path("src/api/infrastructure/providers/research_runtime.py")
PIPELINE_STORE = Path("src/api/infrastructure/orchestration/pipeline_store.py")


def test_action_runtime_provider_uses_scenario_stores_not_orchestration_facade() -> None:
    source = ACTION_RUNTIME_PROVIDER.read_text(encoding="utf-8")

    assert "api.infrastructure.orchestration.store" not in source
    assert "def get_orchestration_store" not in source
    for store_name in (
        "ActionCommandStore",
        "ActionReadStore",
        "ApprovalStore",
        "CampaignStateStore",
        "DispatchStore",
        "EventStore",
        "PipelineOrchestrationStore",
        "RunClaimStore",
        "RunStateStore",
        "ScheduledWorkStore",
    ):
        assert store_name in source


def test_pipeline_store_is_narrow_adapter_over_pipeline_scenarios() -> None:
    source = PIPELINE_STORE.read_text(encoding="utf-8")

    assert "class PipelineOrchestrationStore" in source
    assert "OrchestrationStore" not in source.replace("PipelineOrchestrationStore", "")
    assert "self.run_claims.claim_node_run" in source
    assert "self.scheduled_work.lease_ready_scheduled_node_runs" in source
    assert "self.run_states.mark_run_finished" in source


def test_research_runtime_provider_uses_campaign_state_store_for_lifecycle() -> None:
    source = RESEARCH_RUNTIME_PROVIDER.read_text(encoding="utf-8")

    assert "api.infrastructure.orchestration.store" not in source
    assert "CampaignStateStore" in source
    assert "def get_campaign_lifecycle_reader" in source
    assert "def get_campaign_lifecycle_reconciler" in source
