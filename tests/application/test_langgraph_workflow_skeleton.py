from __future__ import annotations

from uuid import UUID, uuid4

from api.application.langgraph_workflows import (
    LangGraphWorkflowRuntime,
    LangGraphWorkflowState,
    WorkflowStartRequest,
)


class RecordingWorkflowStore:
    def __init__(self) -> None:
        self.workflow_id = uuid4()
        self.run_id = uuid4()
        self.correlation_id = uuid4()
        self.started = []
        self.paused = []
        self.resumed = []
        self.cancelled = []

    async def start_run(self, request: WorkflowStartRequest) -> LangGraphWorkflowState:
        self.started.append(request)
        return LangGraphWorkflowState(
            workflow_id=self.workflow_id,
            run_id=self.run_id,
            program_id=request.program_id,
            campaign_id=request.campaign_id,
            correlation_id=self.correlation_id,
            workflow_type=request.workflow_type,
            status="running",
            current_node=request.entry_node,
            checkpoint_ref=None,
            action_ids=(),
            wait_condition_ids=(),
            result_set_keys=(),
        )

    async def pause_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str,
        current_node: str,
        wait_condition_id: UUID | None,
    ) -> LangGraphWorkflowState:
        self.paused.append((run_id, checkpoint_ref, current_node, wait_condition_id))
        return LangGraphWorkflowState(
            workflow_id=self.workflow_id,
            run_id=run_id,
            program_id=uuid4(),
            campaign_id=None,
            correlation_id=self.correlation_id,
            workflow_type="surface_hypothesis",
            status="waiting",
            current_node=current_node,
            checkpoint_ref=checkpoint_ref,
            action_ids=(),
            wait_condition_ids=(wait_condition_id,) if wait_condition_id else (),
            result_set_keys=(),
        )

    async def resume_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str | None = None,
    ) -> LangGraphWorkflowState:
        self.resumed.append((run_id, checkpoint_ref))
        return LangGraphWorkflowState(
            workflow_id=self.workflow_id,
            run_id=run_id,
            program_id=uuid4(),
            campaign_id=None,
            correlation_id=self.correlation_id,
            workflow_type="surface_hypothesis",
            status="running",
            current_node="resume",
            checkpoint_ref=checkpoint_ref,
            action_ids=(),
            wait_condition_ids=(),
            result_set_keys=(),
        )

    async def cancel_run(
        self,
        *,
        run_id: UUID,
        reason: str | None = None,
    ) -> LangGraphWorkflowState:
        self.cancelled.append((run_id, reason))
        return LangGraphWorkflowState(
            workflow_id=self.workflow_id,
            run_id=run_id,
            program_id=uuid4(),
            campaign_id=None,
            correlation_id=self.correlation_id,
            workflow_type="surface_hypothesis",
            status="cancelled",
            current_node="approval",
            checkpoint_ref="pg-checkpoint:approval",
            action_ids=(),
            wait_condition_ids=(),
            result_set_keys=(),
        )


async def test_langgraph_runtime_state_stores_only_ids_and_pointers() -> None:
    store = RecordingWorkflowStore()
    runtime = LangGraphWorkflowRuntime(store)
    request = WorkflowStartRequest(
        program_id=uuid4(),
        workflow_type="surface_hypothesis",
        entry_node="collect_context",
        campaign_id=uuid4(),
    )

    state = await runtime.start(request)

    assert state.status == "running"
    state_dict = state.to_dict()
    assert set(state_dict) == {
        "workflow_id",
        "run_id",
        "program_id",
        "campaign_id",
        "correlation_id",
        "workflow_type",
        "status",
        "current_node",
        "checkpoint_ref",
        "action_ids",
        "wait_condition_ids",
        "result_set_keys",
    }
    for forbidden in ("raw", "body", "response", "headers", "cookies", "content"):
        assert forbidden not in state_dict


async def test_langgraph_runtime_can_pause_and_resume_by_checkpoint_ref() -> None:
    store = RecordingWorkflowStore()
    runtime = LangGraphWorkflowRuntime(store)
    run_id = uuid4()
    wait_condition_id = uuid4()

    waiting = await runtime.pause(
        run_id=run_id,
        checkpoint_ref="pg-checkpoint:workflow:run:1",
        current_node="wait_for_projections",
        wait_condition_id=wait_condition_id,
    )
    resumed = await runtime.resume(
        run_id=run_id,
        checkpoint_ref=waiting.checkpoint_ref,
    )

    assert waiting.status == "waiting"
    assert waiting.checkpoint_ref == "pg-checkpoint:workflow:run:1"
    assert waiting.wait_condition_ids == (wait_condition_id,)
    assert resumed.status == "running"
    assert store.paused == [
        (run_id, "pg-checkpoint:workflow:run:1", "wait_for_projections", wait_condition_id)
    ]
    assert store.resumed == [(run_id, "pg-checkpoint:workflow:run:1")]


async def test_langgraph_runtime_can_cancel_run_after_rejected_approval() -> None:
    store = RecordingWorkflowStore()
    runtime = LangGraphWorkflowRuntime(store)
    run_id = uuid4()

    cancelled = await runtime.cancel(
        run_id=run_id,
        reason="human rejected action",
    )

    assert cancelled.status == "cancelled"
    assert store.cancelled == [(run_id, "human rejected action")]


def test_langgraph_workflow_module_does_not_import_execution_surfaces() -> None:
    source = open("src/api/application/langgraph_workflows.py", encoding="utf-8").read()

    for forbidden in ("RabbitMQ", "EventBus", "runner", "subprocess", "raw_artifacts"):
        assert forbidden not in source


def test_langgraph_workflow_runtime_is_available_through_di() -> None:
    source = open("src/api/application/di.py", encoding="utf-8").read()

    assert "LangGraphWorkflowStore" in source
    assert "LangGraphWorkflowRuntime" in source
    assert "get_langgraph_workflow_runtime" in source
