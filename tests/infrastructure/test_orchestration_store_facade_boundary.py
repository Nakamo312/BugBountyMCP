from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
STORE = ROOT / "src/api/infrastructure/orchestration/store.py"
CAMPAIGN_ACTIVITY = ROOT / "src/api/infrastructure/orchestration/campaign_activity.py"
CAMPAIGN_LIFECYCLE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_lifecycle_store.py"
CAMPAIGN_WRITE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_write_store.py"
DISPATCH_LEASING = ROOT / "src/api/infrastructure/orchestration/dispatch_leasing.py"
DISPATCH_WRITER = ROOT / "src/api/infrastructure/orchestration/dispatch_writer.py"
ACTION_READ_STORE = ROOT / "src/api/infrastructure/orchestration/action_read_store.py"
ACTION_READ_QUERIES = ROOT / "src/api/infrastructure/orchestration/action_read_queries.py"
ACTION_READ_MAPPERS = ROOT / "src/api/infrastructure/orchestration/action_read_mappers.py"
ACTION_WRITE_HELPERS = ROOT / "src/api/infrastructure/orchestration/action_write_helpers.py"
ACTION_EXECUTION_WRITER = ROOT / "src/api/infrastructure/orchestration/action_execution_writer.py"
RUN_STATE_STORE = ROOT / "src/api/infrastructure/orchestration/run_state_store.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orchestration_compatibility_facade_is_removed() -> None:
    assert not STORE.exists()


def test_scenario_stores_keep_the_moved_behavior() -> None:
    activity_source = _read(CAMPAIGN_ACTIVITY)
    lifecycle_source = _read(CAMPAIGN_LIFECYCLE_STORE)
    write_source = _read(CAMPAIGN_WRITE_STORE)
    lease_source = _read(DISPATCH_LEASING)
    writer_source = _read(DISPATCH_WRITER)
    action_read_source = _read(ACTION_READ_STORE)
    action_read_query_source = _read(ACTION_READ_QUERIES)
    action_read_mapper_source = _read(ACTION_READ_MAPPERS)
    helper_source = _read(ACTION_WRITE_HELPERS)
    execution_source = _read(ACTION_EXECUTION_WRITER)
    run_state_source = _read(RUN_STATE_STORE)

    assert "def campaign_activity_query" in activity_source
    assert "def campaign_activity_from_row" in activity_source
    assert "def validate_terminal_campaign_status" in lifecycle_source
    assert "class CampaignWriteStore" in write_source
    assert "def notify_statement" in writer_source
    assert "async def enqueue_dispatch" in writer_source
    assert "async def claim_dispatches" in lease_source
    assert "def list_action_events_query" in action_read_query_source
    assert "def list_action_artifacts_query" in action_read_query_source
    assert "def action_record_from_row" in action_read_mapper_source
    assert "def action_event_record_from_row" in action_read_mapper_source
    assert "def action_run_result_from_row" in action_read_mapper_source
    assert "def action_artifact_reference_from_row" in action_read_mapper_source
    assert "def scope_status" in helper_source
    assert "def target_status" in helper_source
    assert "def catalog_hash" in helper_source
    assert "async def insert_queued_execution" in execution_source
    assert "insert_event_store_row(session, envelope)" in execution_source
    assert "def retry_values_for_terminal_status" in run_state_source
