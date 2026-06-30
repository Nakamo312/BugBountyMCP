from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.action_outcomes import ActionOutcomeRecorder
from api.application.contracts import (
    ActionOutcomeDraft,
    ActionOutcomeMeasures,
    ActionOutcomeScore,
    ExecutionStatus,
    TerminalOutcome,
)


class FakeScoreCalculator:
    calls: list[dict[str, object]] = []

    @classmethod
    def calculate(cls, *, measures, status, terminal_outcome):
        cls.calls.append(
            {
                "measures": measures,
                "status": status,
                "terminal_outcome": terminal_outcome,
            }
        )
        return ActionOutcomeScore(
            information_gain_score=7.0,
            score_version="test-score-v1",
            score_breakdown={"source": "fake"},
        )


class FakeStore:
    def __init__(self, draft: ActionOutcomeDraft | None) -> None:
        self.draft = draft
        self.loaded_run_id = None
        self.upserted = None

    async def load_run_outcome_draft(self, *, run_id):
        self.loaded_run_id = run_id
        return self.draft

    async def upsert_run_outcome(self, *, draft, score):
        self.upserted = {"draft": draft, "score": score}
        return {"draft": draft, "score": score}

    async def apply_feedback(self, *, action_id, feedback):
        return {"action_id": action_id, "feedback": feedback}


@pytest.mark.asyncio
async def test_action_outcome_recorder_scores_draft_outside_store() -> None:
    run_id = uuid4()
    draft = ActionOutcomeDraft(
        row={"run_id": run_id},
        outcome_id=uuid4(),
        measures=ActionOutcomeMeasures(raw_artifact_count=3, duration_ms=1000),
        status=ExecutionStatus.COMPLETED,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )
    store = FakeStore(draft)
    FakeScoreCalculator.calls = []

    recorder = ActionOutcomeRecorder(store, score_calculator=FakeScoreCalculator)
    record = await recorder.record_finished_run(run_id=run_id)

    assert store.loaded_run_id == run_id
    assert FakeScoreCalculator.calls == [
        {
            "measures": draft.measures,
            "status": ExecutionStatus.COMPLETED,
            "terminal_outcome": TerminalOutcome.COMPLETED,
        }
    ]
    assert store.upserted == record
    assert store.upserted["draft"] is draft
    assert store.upserted["score"].score_version == "test-score-v1"


@pytest.mark.asyncio
async def test_action_outcome_recorder_skips_scoring_when_run_has_no_draft() -> None:
    store = FakeStore(None)
    FakeScoreCalculator.calls = []

    recorder = ActionOutcomeRecorder(store, score_calculator=FakeScoreCalculator)
    record = await recorder.record_finished_run(run_id=uuid4())

    assert record is None
    assert FakeScoreCalculator.calls == []
    assert store.upserted is None
