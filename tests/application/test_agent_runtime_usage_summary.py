from __future__ import annotations

from api.application.agent_runtime_usage import (
    runtime_usage_delta_from_metadata,
    summarize_agent_runtime_usage_aggregates,
)


def test_runtime_usage_delta_extracts_backend_budget_decision() -> None:
    delta = runtime_usage_delta_from_metadata({
        "budget": {
            "requested_mode": "deep",
            "selected_mode": "normal",
            "llm_allowed": True,
            "reason_code": "deep_mode_disabled",
            "deep_approval": {"reason_code": "deep_mode_disabled"},
            "observed": {
                "prompt_chars_before": 1000,
                "prompt_chars_after": 800,
                "context_refs_before": 10,
                "context_refs_after": 5,
            },
        }
    })

    assert delta is not None
    assert delta.requested_mode == "deep"
    assert delta.selected_mode == "normal"
    assert delta.downgraded is True
    assert delta.deep_downgraded is True
    assert delta.context_truncated is True


def test_runtime_usage_aggregate_summary_preserves_existing_ui_shape() -> None:
    summary = summarize_agent_runtime_usage_aggregates([
        {
            "program_id": "p",
            "campaign_id": "c",
            "usage_date": "2026-06-26",
            "total_agent_messages": 2,
            "runtime_decision_messages": 2,
            "selected_modes": {"none": 1, "cheap": 0, "normal": 1, "deep": 0},
            "requested_modes": {"none": 1, "cheap": 0, "normal": 0, "deep": 1},
            "llm_allowed_messages": 1,
            "no_model_messages": 1,
            "downgraded_messages": 1,
            "deep_requested_messages": 1,
            "deep_approved_messages": 0,
            "deep_downgraded_messages": 1,
            "context_truncated_messages": 1,
            "latest_selected_mode": "normal",
            "latest_requested_mode": "deep",
            "latest_reason_code": "deep_mode_disabled",
        }
    ])

    assert summary.runtime_decision_messages == 2
    assert summary.selected_modes == {"none": 1, "cheap": 0, "normal": 1, "deep": 0}
    assert summary.requested_modes["deep"] == 1
    assert summary.deep_downgraded_messages == 1
    assert "runtime_mode_downgraded" in summary.warnings
