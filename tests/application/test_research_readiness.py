from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.agent_wait_conditions import WaitConditionDecision
from api.application.hypotheses import HypothesisBuildRequest
from api.application.research_readiness import (
    ResearchReadinessGate,
    ResearchReadinessReason,
)
from api.application.projections import ProjectionKey


class RecordingWaitEngine:
    def __init__(self, decisions) -> None:
        self.decisions = list(decisions)
        self.conditions = []

    async def evaluate(self, condition):
        self.conditions.append(condition)
        return self.decisions.pop(0)


class RecordingProtocolStore:
    def __init__(self) -> None:
        self.created = []
        self.condition_id = uuid4()

    async def create_wait_condition(self, **kwargs):
        self.created.append(kwargs)
        return self.condition_id


class RecordingWorkflowRuntime:
    def __init__(self) -> None:
        self.paused = []
        self.resumed = []

    async def pause(self, **kwargs):
        self.paused.append(kwargs)

    async def resume(self, **kwargs):
        self.resumed.append(kwargs)


async def test_readiness_gate_persists_projection_wait_before_result_set_wait() -> None:
    program_id = uuid4()
    workflow_run_id = uuid4()
    engine = RecordingWaitEngine(
        [
            WaitConditionDecision(
                resolved=False,
                reason="projections_not_ready",
                payload={"missing": [{"projection_type": "opensearch"}]},
            )
        ]
    )
    store = RecordingProtocolStore()
    gate = ResearchReadinessGate(wait_engine=engine, protocol_store=store)

    decision = await gate.evaluate(
        HypothesisBuildRequest(
            program_id=program_id,
            workflow_run_id=workflow_run_id,
            result_key="surface:admin",
        ),
        required_projections=(ProjectionKey("opensearch", "http-observations"),),
    )

    assert decision.ready is False
    assert decision.reason == "projections_not_ready"
    assert decision.reason_code == ResearchReadinessReason.PROJECTION_MISSING
    assert decision.wait_condition_type == "projections_ready"
    assert decision.wait_condition_id == store.condition_id
    assert len(engine.conditions) == 1
    assert engine.conditions[0].condition_type == "projections_ready"
    assert store.created[0]["workflow_run_id"] == workflow_run_id
    assert store.created[0]["condition_type"] == "projections_ready"


async def test_readiness_gate_waits_for_result_set_after_projections_are_ready() -> None:
    workflow_run_id = uuid4()
    engine = RecordingWaitEngine(
        [
            WaitConditionDecision(
                resolved=True,
                reason="projections_ready",
            ),
            WaitConditionDecision(
                resolved=False,
                reason="result_sets_not_ready",
                payload={"result_set_keys": []},
            ),
        ]
    )
    store = RecordingProtocolStore()
    gate = ResearchReadinessGate(wait_engine=engine, protocol_store=store)

    decision = await gate.evaluate(
        HypothesisBuildRequest(
            program_id=uuid4(),
            workflow_run_id=workflow_run_id,
            action_id=uuid4(),
        ),
        required_projections=(ProjectionKey("opensearch", "http-observations"),),
    )

    assert decision.ready is False
    assert decision.reason == "result_sets_not_ready"
    assert decision.reason_code == ResearchReadinessReason.RESULT_SETS_NOT_READY
    assert decision.wait_condition_type == "new_facts_available"
    assert [condition.condition_type for condition in engine.conditions] == [
        "projections_ready",
        "new_facts_available",
    ]
    assert store.created[0]["condition_type"] == "new_facts_available"
    assert store.created[0]["required_state"]["action_id"]


async def test_readiness_gate_returns_ready_without_creating_wait_condition() -> None:
    engine = RecordingWaitEngine(
        [
            WaitConditionDecision(resolved=True, reason="projections_ready"),
            WaitConditionDecision(
                resolved=True,
                reason="result_sets_ready",
                payload={"result_set_keys": ["surface:admin"]},
            ),
        ]
    )
    store = RecordingProtocolStore()
    gate = ResearchReadinessGate(wait_engine=engine, protocol_store=store)

    decision = await gate.evaluate(
        HypothesisBuildRequest(
            program_id=uuid4(),
            workflow_run_id=uuid4(),
            result_key="surface:admin",
        ),
        required_projections=(ProjectionKey("opensearch", "http-observations"),),
    )

    assert decision.ready is True
    assert decision.reason == "research_inputs_ready"
    assert decision.reason_code == ResearchReadinessReason.READY
    assert decision.result_set_keys == ("surface:admin",)
    assert store.created == []


async def test_readiness_gate_updates_durable_workflow_wait_and_resume_state() -> None:
    workflow_run_id = uuid4()
    runtime = RecordingWorkflowRuntime()
    engine = RecordingWaitEngine(
        [
            WaitConditionDecision(
                resolved=False,
                reason="result_sets_not_ready",
                payload={"result_set_keys": []},
            ),
            WaitConditionDecision(
                resolved=True,
                reason="result_sets_ready",
                payload={"result_set_keys": ["surface:admin"]},
            ),
        ]
    )
    store = RecordingProtocolStore()
    gate = ResearchReadinessGate(
        wait_engine=engine,
        protocol_store=store,
        workflow_runtime=runtime,
    )
    request = HypothesisBuildRequest(
        program_id=uuid4(),
        workflow_run_id=workflow_run_id,
        result_key="surface:admin",
    )

    waiting = await gate.evaluate(request, required_projections=())
    ready = await gate.evaluate(request, required_projections=())

    assert waiting.ready is False
    assert waiting.reason_code == ResearchReadinessReason.RESULT_SETS_NOT_READY
    assert ready.ready is True
    assert runtime.paused == [
        {
            "run_id": workflow_run_id,
            "checkpoint_ref": f"langgraph:{workflow_run_id}",
            "current_node": "wait_for_readiness",
            "wait_condition_id": store.condition_id,
        }
    ]
    assert runtime.resumed == [
        {
            "run_id": workflow_run_id,
            "checkpoint_ref": f"langgraph:{workflow_run_id}",
        }
    ]


async def test_readiness_gate_distinguishes_failed_and_lagging_projection_reasons() -> None:
    workflow_run_id = uuid4()
    for payload, expected in (
        (
            {"failed": [{"projection_type": "opensearch"}]},
            ResearchReadinessReason.PROJECTION_FAILED,
        ),
        (
            {"lagging": [{"projection_type": "neo4j"}]},
            ResearchReadinessReason.PROJECTION_LAGGING,
        ),
    ):
        engine = RecordingWaitEngine(
            [
                WaitConditionDecision(
                    resolved=False,
                    reason="projections_not_ready",
                    payload=payload,
                )
            ]
        )
        store = RecordingProtocolStore()
        gate = ResearchReadinessGate(wait_engine=engine, protocol_store=store)

        decision = await gate.evaluate(
            HypothesisBuildRequest(
                program_id=uuid4(),
                workflow_run_id=workflow_run_id,
                result_key="surface:admin",
            ),
            required_projections=(ProjectionKey("opensearch", "http-observations"),),
        )

        assert decision.ready is False
        assert decision.reason_code == expected
        assert decision.wait_condition_type == "projections_ready"


async def test_readiness_gate_uses_explicit_reason_for_missing_durable_run_id() -> None:
    engine = RecordingWaitEngine(
        [
            WaitConditionDecision(
                resolved=False,
                reason="result_sets_not_ready",
                payload={"result_set_keys": []},
            )
        ]
    )
    gate = ResearchReadinessGate(
        wait_engine=engine,
        protocol_store=RecordingProtocolStore(),
    )

    with pytest.raises(
        ValueError,
        match=ResearchReadinessReason.DURABLE_WAIT_REQUIRES_WORKFLOW_RUN,
    ):
        await gate.evaluate(
            HypothesisBuildRequest(program_id=uuid4(), result_key="surface:admin"),
            required_projections=(),
        )


def test_readiness_gate_is_wired_to_existing_projection_and_agent_stores() -> None:
    source = open("src/api/infrastructure/providers/research_runtime.py", encoding="utf-8").read()

    assert "get_projection_state_store" in source
    assert "get_agent_wait_condition_engine" in source
    assert "get_research_readiness_gate" in source
    assert "readiness_gate=readiness_gate" in source
