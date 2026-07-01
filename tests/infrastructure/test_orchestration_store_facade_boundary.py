from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
STORE = ROOT / "src/api/infrastructure/orchestration/store.py"
CAMPAIGN_STATE_STORE = ROOT / "src/api/infrastructure/orchestration/campaign_state_store.py"
DISPATCH_STORE = ROOT / "src/api/infrastructure/orchestration/dispatch_store.py"
ACTION_READ_STORE = ROOT / "src/api/infrastructure/orchestration/action_read_store.py"
ACTION_WRITE_HELPERS = ROOT / "src/api/infrastructure/orchestration/action_write_helpers.py"
RUN_STATE_STORE = ROOT / "src/api/infrastructure/orchestration/run_state_store.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_orchestration_store_is_deprecated_compatibility_facade_only() -> None:
    store_source = _read(STORE)
    campaign_source = _read(CAMPAIGN_STATE_STORE)
    dispatch_source = _read(DISPATCH_STORE)
    action_read_source = _read(ACTION_READ_STORE)
    helper_source = _read(ACTION_WRITE_HELPERS)
    run_state_source = _read(RUN_STATE_STORE)

    assert "deprecated_compatibility_facade = True" in store_source
    assert "DeprecationWarning" not in store_source
    assert "Adding methods here keeps the old one-object-knows-everything model alive" in store_source

    for helper in (
        "def _campaign_activity_query",
        "def _campaign_activity_from_row",
        "def _persist_campaign_lifecycle",
        "def _validate_terminal_campaign_status",
        "def _scope_status",
        "def _target_status",
        "def _catalog_hash",
        "def _event_dispatch_notify_statement",
        "def _enqueue_dispatch",
        "def _action_record_from_row",
        "def _action_event_record_from_row",
        "def _action_run_result_from_row",
        "def _action_artifact_reference_from_row",
        "def _retry_values",
    ):
        assert helper not in store_source

    assert "def activity_query" in campaign_source
    assert "def activity_from_row" in campaign_source
    assert "def validate_terminal_campaign_status" in campaign_source
    assert "def notify_statement" in dispatch_source
    assert "async def enqueue_dispatch" in dispatch_source
    assert "def action_record_from_row" in action_read_source
    assert "def action_event_record_from_row" in action_read_source
    assert "def action_run_result_from_row" in action_read_source
    assert "def action_artifact_reference_from_row" in action_read_source
    assert "def scope_status" in helper_source
    assert "def target_status" in helper_source
    assert "def catalog_hash" in helper_source
    assert "def retry_values_for_terminal_status" in run_state_source
