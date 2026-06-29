from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api.application.agent_wait_conditions import (
    AgentWaitCondition,
    AgentWaitConditionEngine,
    AgentWaitConditionProcessor,
    AgentWaitConditionRecord,
    RunWaitState,
    WaitConditionDecision,
)
from api.application.campaign_lifecycle import CampaignLifecycleDecision
from api.application.projections import ProjectionKey, ProjectionLagState


OPENSEARCH_HTTP = ProjectionKey("opensearch", "http-observations")


class StubProjectionReader:
    def __init__(self, states: list[ProjectionLagState]) -> None:
        self.states = states
        self.calls = []

    async def list_states(self, *, program_id, required):
        self.calls.append((program_id, tuple(required)))
        return self.states


class StubResultSetReader:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.calls = []

    async def list_result_sets(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows


class StubExecutionStateReader:
    def __init__(self, state: RunWaitState | None) -> None:
        self.state = state
        self.calls = []

    async def get_run_state(self, *, program_id, run_id):
        self.calls.append((program_id, run_id))
        return self.state


class StubCampaignLifecycleReader:
    def __init__(self, decision: CampaignLifecycleDecision) -> None:
        self.decision = decision
        self.calls = []

    async def reconcile_campaign_lifecycle(self, **kwargs):
        self.calls.append(kwargs)
        return self.decision


async def test_projections_ready_wait_resolves_only_when_required_projections_are_ready() -> None:
    program_id = uuid4()
    reader = StubProjectionReader(
        [ProjectionLagState(OPENSEARCH_HTTP, "ready", "42", "42", 0)]
    )
    engine = AgentWaitConditionEngine(projection_reader=reader)
    condition = AgentWaitCondition(
        condition_type="projections_ready",
        program_id=program_id,
        required_state={
            "projections": [
                {"projection_type": "opensearch", "projection_name": "http-observations"}
            ]
        },
    )

    decision = await engine.evaluate(condition)

    assert decision == WaitConditionDecision(
        resolved=True,
        reason="projections_ready",
        payload={"missing": [], "lagging": [], "failed": []},
    )
    assert reader.calls == [(program_id, (OPENSEARCH_HTTP,))]


async def test_projections_ready_wait_stays_pending_when_projection_lags() -> None:
    reader = StubProjectionReader(
        [ProjectionLagState(OPENSEARCH_HTTP, "observed", "43", "42", 1)]
    )
    engine = AgentWaitConditionEngine(projection_reader=reader)
    condition = AgentWaitCondition(
        condition_type="projections_ready",
        program_id=uuid4(),
        required_state={
            "projections": [
                {"projection_type": "opensearch", "projection_name": "http-observations"}
            ]
        },
    )

    decision = await engine.evaluate(condition)

    assert decision.resolved is False
    assert decision.reason == "projections_not_ready"
    assert decision.payload == {
        "missing": [],
        "lagging": [{"projection_type": "opensearch", "projection_name": "http-observations"}],
        "failed": [],
    }


async def test_campaign_quiescent_wait_resolves_from_campaign_lifecycle() -> None:
    campaign_id = uuid4()
    program_id = uuid4()
    reader = StubCampaignLifecycleReader(
        CampaignLifecycleDecision(
            status="quiescent",
            reason="campaign_quiescent",
            quiescent=True,
            quiet_for_seconds=31,
        )
    )
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        campaign_lifecycle_reader=reader,
        campaign_quiet_window_seconds=30,
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="campaign_quiescent",
            program_id=program_id,
            required_state={"campaign_id": str(campaign_id)},
        )
    )

    assert decision.resolved is True
    assert decision.reason == "campaign_quiescent"
    assert decision.payload["status"] == "quiescent"
    assert reader.calls[0]["campaign_id"] == campaign_id
    assert reader.calls[0]["program_id"] == program_id
    assert reader.calls[0]["quiet_window_seconds"] == 30


async def test_campaign_quiescent_wait_stays_pending_during_quiet_window() -> None:
    reader = StubCampaignLifecycleReader(
        CampaignLifecycleDecision(
            status="waiting_for_projections",
            reason="quiet_window",
            quiescent=False,
            quiet_for_seconds=10,
        )
    )
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        campaign_lifecycle_reader=reader,
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="campaign_quiescent",
            program_id=uuid4(),
            required_state={"campaign_id": str(uuid4())},
        )
    )

    assert decision.resolved is False
    assert decision.reason == "quiet_window"


async def test_tool_run_completed_resolves_for_terminal_failed_run() -> None:
    program_id = uuid4()
    run_id = uuid4()
    reader = StubExecutionStateReader(
        RunWaitState(
            run_id=run_id,
            status="failed",
            terminal_outcome="tool_failed",
        )
    )
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        execution_state_reader=reader,
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="tool_run_completed",
            program_id=program_id,
            required_state={"run_id": str(run_id)},
        )
    )

    assert decision == WaitConditionDecision(
        resolved=True,
        reason="tool_run_terminal",
        payload={
            "run_id": str(run_id),
            "status": "failed",
            "terminal_outcome": "tool_failed",
        },
    )
    assert reader.calls == [(program_id, run_id)]


async def test_tool_run_completed_stays_pending_for_flushing_run() -> None:
    run_id = uuid4()
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        execution_state_reader=StubExecutionStateReader(
            RunWaitState(run_id=run_id, status="flushing", terminal_outcome=None)
        ),
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="tool_run_completed",
            program_id=uuid4(),
            required_state={"run_id": str(run_id)},
        )
    )

    assert decision.resolved is False
    assert decision.reason == "tool_run_not_terminal"


async def test_ingestion_completed_resolves_only_after_successful_run_completion() -> None:
    run_id = uuid4()
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        execution_state_reader=StubExecutionStateReader(
            RunWaitState(
                run_id=run_id,
                status="completed",
                terminal_outcome="completed",
            )
        ),
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="ingestion_completed",
            program_id=uuid4(),
            required_state={"run_id": str(run_id)},
        )
    )

    assert decision.resolved is True
    assert decision.reason == "ingestion_completed"
    assert decision.payload["run_id"] == str(run_id)


async def test_ingestion_completed_does_not_resolve_failed_run() -> None:
    run_id = uuid4()
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        execution_state_reader=StubExecutionStateReader(
            RunWaitState(
                run_id=run_id,
                status="failed",
                terminal_outcome="tool_failed",
            )
        ),
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="ingestion_completed",
            program_id=uuid4(),
            required_state={"run_id": str(run_id)},
        )
    )

    assert decision.resolved is False
    assert decision.reason == "ingestion_not_completed"


async def test_run_wait_predicate_rejects_invalid_run_id_without_crashing_sweep() -> None:
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        execution_state_reader=StubExecutionStateReader(None),
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="tool_run_completed",
            program_id=uuid4(),
            required_state={"run_id": "not-a-uuid"},
        )
    )

    assert decision.resolved is False
    assert decision.reason == "invalid_run_id"


async def test_new_facts_available_wait_resolves_from_program_scoped_result_sets() -> None:
    program_id = uuid4()
    workflow_run_id = uuid4()
    result_sets = StubResultSetReader(
        [{"result_key": "surface:admin", "program_id": program_id}]
    )
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        result_set_reader=result_sets,
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="new_facts_available",
            program_id=program_id,
            required_state={
                "result_key": "surface:admin",
                "workflow_run_id": str(workflow_run_id),
            },
        )
    )

    assert decision == WaitConditionDecision(
        resolved=True,
        reason="result_sets_ready",
        payload={"result_set_keys": ["surface:admin"]},
    )
    assert result_sets.calls[0]["program_id"] == program_id
    assert result_sets.calls[0]["result_key"] == "surface:admin"
    assert result_sets.calls[0]["workflow_run_id"] == workflow_run_id


async def test_new_facts_available_wait_stays_pending_without_result_sets() -> None:
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader([]),
        result_set_reader=StubResultSetReader([]),
    )

    decision = await engine.evaluate(
        AgentWaitCondition(
            condition_type="new_facts_available",
            program_id=uuid4(),
            required_state={"action_id": str(uuid4())},
        )
    )

    assert decision.resolved is False
    assert decision.reason == "result_sets_not_ready"
    assert decision.payload == {"result_set_keys": []}


class RecordingConditionStore:
    def __init__(
        self,
        records: list[AgentWaitConditionRecord],
        resume_records: list[AgentWaitConditionRecord] | None = None,
    ) -> None:
        self.records = records
        self.resume_records = resume_records or []
        self.resolved = []
        self.timed_out = []
        self.list_calls = 0

    async def list_pending(self, *, limit: int, now):
        self.list_calls += 1
        return self.records[:limit]

    async def list_resume_ready(self, *, limit: int):
        return self.resume_records[:limit]

    async def mark_resolved(self, *, condition_id, payload):
        self.resolved.append((condition_id, payload))
        return True

    async def mark_timed_out(self, *, condition_id, payload):
        self.timed_out.append((condition_id, payload))
        return True


class RecordingWorkflowResumer:
    def __init__(self) -> None:
        self.records = []

    async def resume(self, record):
        self.records.append(record)


class RecordingCampaignLifecycleReconciler:
    def __init__(self) -> None:
        self.calls = []

    async def reconcile_active_campaigns(self, **kwargs):
        self.calls.append(kwargs)
        return 0


async def test_wait_condition_processor_persists_resolved_projection_waits() -> None:
    condition_id = uuid4()
    store = RecordingConditionStore(
        [
            AgentWaitConditionRecord(
                condition_id=condition_id,
                condition_key="mvp-research:projections_ready:abc",
                condition_type="projections_ready",
                program_id=uuid4(),
                workflow_run_id=uuid4(),
                required_state={
                    "projections": [
                        {"projection_type": "opensearch", "projection_name": "http-observations"}
                    ]
                },
            )
        ]
    )
    engine = AgentWaitConditionEngine(
        projection_reader=StubProjectionReader(
            [ProjectionLagState(OPENSEARCH_HTTP, "ready", "42", "42", 0)]
        )
    )
    processor = AgentWaitConditionProcessor(store=store, engine=engine)

    transitions = await processor.process_once(limit=10)

    assert transitions == 1
    assert store.resolved == [
        (condition_id, {"missing": [], "lagging": [], "failed": []})
    ]
    assert store.timed_out == []


async def test_wait_condition_processor_auto_resumes_only_after_winning_terminal_transition() -> None:
    workflow_run_id = uuid4()
    record = AgentWaitConditionRecord(
        condition_id=uuid4(),
        condition_key="mvp-research:new_facts_available:abc",
        condition_type="new_facts_available",
        program_id=uuid4(),
        workflow_run_id=workflow_run_id,
        required_state={"result_key": "surface:admin"},
    )
    store = RecordingConditionStore([record])
    resumer = RecordingWorkflowResumer()
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(
            projection_reader=StubProjectionReader([]),
            result_set_reader=StubResultSetReader(
                [{"result_key": "surface:admin"}]
            ),
        ),
        workflow_resumer=resumer,
    )

    transitions = await processor.process_once()

    assert transitions == 1
    assert resumer.records == [record]


async def test_wait_condition_processor_auto_resumes_research_prefix_waits() -> None:
    workflow_run_id = uuid4()
    record = AgentWaitConditionRecord(
        condition_id=uuid4(),
        condition_key="research:new_facts_available:abc",
        condition_type="new_facts_available",
        program_id=uuid4(),
        workflow_run_id=workflow_run_id,
        required_state={"result_key": "surface:admin"},
    )
    store = RecordingConditionStore([record])
    resumer = RecordingWorkflowResumer()
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(
            projection_reader=StubProjectionReader([]),
            result_set_reader=StubResultSetReader(
                [{"result_key": "surface:admin"}]
            ),
        ),
        workflow_resumer=resumer,
    )

    transitions = await processor.process_once()

    assert transitions == 1
    assert resumer.records == [record]


async def test_wait_condition_processor_does_not_resume_when_another_worker_won() -> None:
    class LostTransitionStore(RecordingConditionStore):
        async def mark_resolved(self, *, condition_id, payload):
            self.resolved.append((condition_id, payload))
            return False

    record = AgentWaitConditionRecord(
        condition_id=uuid4(),
        condition_key="mvp-research:projections_ready:abc",
        condition_type="projections_ready",
        program_id=uuid4(),
        workflow_run_id=uuid4(),
        required_state={"projections": []},
    )
    store = LostTransitionStore([record])
    resumer = RecordingWorkflowResumer()
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(projection_reader=StubProjectionReader([])),
        workflow_resumer=resumer,
    )

    transitions = await processor.process_once()

    assert transitions == 0
    assert resumer.records == []


async def test_wait_condition_processor_retries_resolved_wait_for_waiting_workflow() -> None:
    record = AgentWaitConditionRecord(
        condition_id=uuid4(),
        condition_key="mvp-research:new_facts_available:retry",
        condition_type="new_facts_available",
        program_id=uuid4(),
        workflow_run_id=uuid4(),
    )
    store = RecordingConditionStore([], resume_records=[record])
    resumer = RecordingWorkflowResumer()
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(projection_reader=StubProjectionReader([])),
        workflow_resumer=resumer,
    )

    transitions = await processor.process_once()

    assert transitions == 0
    assert resumer.records == [record]


async def test_wait_condition_processor_persists_deadline_timeouts_without_evaluating() -> None:
    now = datetime.now(timezone.utc)
    condition_id = uuid4()
    reader = StubProjectionReader(
        [ProjectionLagState(OPENSEARCH_HTTP, "ready", "42", "42", 0)]
    )
    store = RecordingConditionStore(
        [
            AgentWaitConditionRecord(
                condition_id=condition_id,
                condition_key="mvp-research:projections_ready:timeout",
                condition_type="projections_ready",
                program_id=uuid4(),
                workflow_run_id=uuid4(),
                required_state={
                    "projections": [
                        {"projection_type": "opensearch", "projection_name": "http-observations"}
                    ]
                },
                deadline_at=now - timedelta(seconds=1),
            )
        ]
    )
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(projection_reader=reader),
    )

    transitions = await processor.process_once(limit=10, now=now)

    assert transitions == 1
    assert store.resolved == []
    assert store.timed_out == [
        (condition_id, {"reason": "deadline_elapsed"})
    ]
    assert reader.calls == []


async def test_wait_condition_processor_background_lifecycle_runs_periodic_sweeps() -> None:
    store = RecordingConditionStore([])
    processor = AgentWaitConditionProcessor(
        store=store,
        engine=AgentWaitConditionEngine(projection_reader=StubProjectionReader([])),
        sweep_interval_seconds=0.01,
    )

    await processor.start()
    await asyncio.sleep(0.035)
    await processor.stop()

    assert store.list_calls >= 2
    assert processor.running is False


async def test_wait_condition_processor_reconciles_campaigns_each_sweep() -> None:
    lifecycle = RecordingCampaignLifecycleReconciler()
    processor = AgentWaitConditionProcessor(
        store=RecordingConditionStore([]),
        engine=AgentWaitConditionEngine(projection_reader=StubProjectionReader([])),
        campaign_lifecycle_reconciler=lifecycle,
        campaign_quiet_window_seconds=30,
    )
    now = datetime.now(timezone.utc)

    transitions = await processor.process_once(limit=7, now=now)

    assert transitions == 0
    assert lifecycle.calls == [
        {
            "now": now,
            "quiet_window_seconds": 30,
            "limit": 7,
        }
    ]
