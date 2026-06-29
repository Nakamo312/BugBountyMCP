from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

pytest.importorskip("sqlalchemy")

from api.application.contracts import (
    ActionOutcomeFeedback,
    ActionOutcomeMeasures,
    ExecutionStatus,
    TerminalOutcome,
)
from api.application.action_outcome_scoring import ActionOutcomeScoreCalculator
from api.infrastructure.action_outcomes import ActionOutcomeStore
from api.infrastructure.adapters.orm import action_outcome_feedback_events, action_outcomes


def test_action_outcomes_table_is_declared_as_action_utility_memory() -> None:
    assert "program_id" in action_outcomes.c
    assert "campaign_id" in action_outcomes.c
    assert "action_id" in action_outcomes.c
    assert "job_id" in action_outcomes.c
    assert "run_id" in action_outcomes.c
    assert "capability_id" in action_outcomes.c
    assert "profile_id" in action_outcomes.c
    assert "raw_artifact_count" in action_outcomes.c
    assert "http_observation_count" in action_outcomes.c
    assert "javascript_reference_count" in action_outcomes.c
    assert "observed_endpoints_count" in action_outcomes.c
    assert "new_endpoints_count" in action_outcomes.c
    assert "new_surface_nodes_count" in action_outcomes.c
    assert "new_graph_facts_count" in action_outcomes.c
    assert "new_search_documents_count" in action_outcomes.c
    assert "manual_interest" in action_outcomes.c
    assert "manual_stop" in action_outcomes.c
    assert "continued_by_followup" in action_outcomes.c
    assert "report_created" in action_outcomes.c
    assert "triage_outcome" in action_outcomes.c
    assert "information_gain_score" in action_outcomes.c
    assert "score_breakdown" in action_outcomes.c
    assert any(index.name == "idx_action_outcomes_program_score" for index in action_outcomes.indexes)
    assert any(index.name == "idx_action_outcomes_capability_profile" for index in action_outcomes.indexes)


def test_action_outcome_migration_adds_only_generic_utility_memory() -> None:
    source = Path("alembic/versions/k7l8m9n0o1p2_add_action_outcome_memory.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "j6k7l8m9n0o1"' in source
    assert "action_outcomes" in source
    assert "information_gain_score" in source
    assert "manual_interest" in source
    assert "new_surface_nodes_count" in source
    assert "new_graph_facts_count" in source
    assert "new_search_documents_count" in source
    forbidden_bug_classes = ["idor", "ssrf", "takeover", "auth bypass"]
    assert not any(token in source.lower() for token in forbidden_bug_classes)


def test_score_calculator_rewards_information_gain_without_bug_class_rules() -> None:
    low_gain = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(raw_artifact_count=1, duration_ms=1000),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )
    higher_gain = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(
            raw_artifact_count=1,
            http_observation_count=10,
            javascript_reference_count=4,
            observed_hosts_count=2,
            observed_services_count=3,
            observed_endpoints_count=8,
            duration_ms=1000,
        ),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )

    assert higher_gain.score_version == "action-outcome-raw-utility.v2"
    assert higher_gain.information_gain_score > low_gain.information_gain_score
    assert "observation_units" in higher_gain.score_breakdown
    assert "terminal_penalty" in higher_gain.score_breakdown
    assert higher_gain.score_breakdown["diagnostic_projection_novelty"]["scoring_role"] == "telemetry_only"



def test_score_calculator_does_not_reward_projection_counts_as_quality() -> None:
    baseline = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(raw_artifact_count=1, http_observation_count=1, duration_ms=1000),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )
    with_projection_counts = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(
            raw_artifact_count=1,
            http_observation_count=1,
            new_hosts_count=100,
            new_services_count=100,
            new_endpoints_count=100,
            new_surface_nodes_count=100,
            new_graph_facts_count=100,
            new_search_documents_count=100,
            duration_ms=1000,
        ),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )

    assert with_projection_counts.information_gain_score == baseline.information_gain_score
    assert with_projection_counts.score_breakdown["diagnostic_projection_novelty"]["new_endpoints_count"] == 100


def test_score_calculator_penalizes_failed_repetitive_runs() -> None:
    completed = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(raw_artifact_count=2, http_observation_count=3, duration_ms=1000),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )
    failed = ActionOutcomeScoreCalculator.calculate(
        measures=ActionOutcomeMeasures(
            raw_artifact_count=2,
            http_observation_count=3,
            duration_ms=120_000,
            error_count=1,
        ),
        status=ExecutionStatus.FAILED,
        terminal_outcome=TerminalOutcome.TOOL_FAILED,
    )

    assert failed.information_gain_score < completed.information_gain_score
    assert failed.score_breakdown["error_penalty"] > 0
    assert failed.score_breakdown["terminal_penalty"] > 0


def test_action_outcome_store_duration_and_target_count_helpers() -> None:
    start = datetime.now(timezone.utc)
    finish = start + timedelta(seconds=2, milliseconds=500)

    assert ActionOutcomeStore._duration_ms(start, finish) == 2500
    assert ActionOutcomeStore._duration_ms(None, finish) is None
    assert ActionOutcomeStore._target_count({"target_count": 4}) == 4
    assert ActionOutcomeStore._target_count({"target_count": None, "run_payload": {"targets": ["a", "b"]}}) == 2
    assert ActionOutcomeStore._target_count({"target_count": None, "run_payload": {"target": "a"}}) == 1
    assert ActionOutcomeStore._target_count({"target_count": None, "run_payload": {}}) is None


def test_action_outcome_feedback_table_keeps_human_signals_auditable() -> None:
    assert "outcome_id" in action_outcome_feedback_events.c
    assert "action_id" in action_outcome_feedback_events.c
    assert "run_id" in action_outcome_feedback_events.c
    assert "manual_interest" in action_outcome_feedback_events.c
    assert "manual_stop" in action_outcome_feedback_events.c
    assert "continued_by_followup" in action_outcome_feedback_events.c
    assert "report_created" in action_outcome_feedback_events.c
    assert "triage_outcome" in action_outcome_feedback_events.c
    assert "actor" in action_outcome_feedback_events.c
    assert "reason" in action_outcome_feedback_events.c
    assert "confidence" in action_outcome_feedback_events.c
    assert any(index.name == "idx_action_outcome_feedback_action_created" for index in action_outcome_feedback_events.indexes)
    assert any(index.name == "idx_action_outcome_feedback_run_created" for index in action_outcome_feedback_events.indexes)


def test_action_outcome_feedback_migration_adds_audit_trail_without_bug_rules() -> None:
    source = Path("alembic/versions/l8m9n0o1p2q3_add_action_outcome_feedback.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "k7l8m9n0o1p2"' in source
    assert "action_outcome_feedback_events" in source
    assert "manual_interest" in source
    assert "manual_stop" in source
    assert "continued_by_followup" in source
    assert "report_created" in source
    assert "triage_outcome" in source
    assert "ck_action_outcome_feedback_has_signal" in source
    forbidden_bug_classes = ["idor", "ssrf", "takeover", "auth bypass"]
    assert not any(token in source.lower() for token in forbidden_bug_classes)


def test_action_outcome_feedback_contract_requires_generic_signal() -> None:
    with pytest.raises(ValidationError):
        ActionOutcomeFeedback(actor="analyst")

    feedback = ActionOutcomeFeedback(
        manual_interest=True,
        actor="analyst",
        source="ui",
        reason="continue this branch",
        confidence=0.8,
    )

    assert feedback.manual_interest is True
    assert feedback.actor == "analyst"
    assert feedback.source == "ui"
    assert feedback.confidence == 0.8


def test_action_outcome_feedback_helpers_patch_only_present_signals() -> None:
    now = datetime.now(timezone.utc)
    feedback = ActionOutcomeFeedback(
        manual_interest=True,
        manual_stop=False,
        actor="analyst",
        source="ui",
        reason="useful follow-up",
    )

    values = ActionOutcomeStore._feedback_update_values(feedback=feedback, now=now)

    assert values["manual_interest"] is True
    assert values["manual_stop"] is False
    assert "continued_by_followup" not in values
    assert values["updated_at"] == now


def test_action_outcome_feedback_event_values_keep_provenance() -> None:
    now = datetime.now(timezone.utc)
    row = {
        "outcome_id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "action_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
    }
    feedback_id = uuid4()
    feedback = ActionOutcomeFeedback(
        continued_by_followup=True,
        actor="analyst",
        source="ui",
        reason="new endpoints appeared",
        confidence=0.9,
    )

    values = ActionOutcomeStore._feedback_event_values(
        row=row,
        feedback_id=feedback_id,
        feedback=feedback,
        now=now,
    )

    assert values["id"] == feedback_id
    assert values["outcome_id"] == row["outcome_id"]
    assert values["continued_by_followup"] is True
    assert values["actor"] == "analyst"
    assert values["source"] == "ui"
    assert values["reason"] == "new endpoints appeared"
    assert values["confidence"] == 0.9
