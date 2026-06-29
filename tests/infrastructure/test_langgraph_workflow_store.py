from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.application.langgraph_workflows import WorkflowStartRequest
from api.infrastructure.agent_coordination import LangGraphWorkflowStore


class FakeResult:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def mappings(self):
        return self

    def one(self):
        return self._rows[0]


class FakeSession:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.rows)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_langgraph_workflow_store_creates_workflow_and_run_in_one_unit() -> None:
    workflow_id = uuid4()
    run_id = uuid4()
    program_id = uuid4()
    correlation_id = uuid4()
    session = FakeSession(
        [
            {
                "workflow_id": workflow_id,
                "run_id": run_id,
                "program_id": program_id,
                "campaign_id": None,
                "correlation_id": correlation_id,
                "workflow_type": "surface_hypothesis",
                "status": "running",
                "current_node": "collect_context",
                "checkpoint_ref": None,
                "metadata": {"action_ids": [], "wait_condition_ids": [], "result_set_keys": []},
            }
        ]
    )
    store = LangGraphWorkflowStore(FakeSessionFactory(session))

    state = await store.start_run(
        WorkflowStartRequest(
            program_id=program_id,
            workflow_type="surface_hypothesis",
            entry_node="collect_context",
        )
    )

    assert state.workflow_id == workflow_id
    assert state.run_id == run_id
    assert state.status == "running"
    assert session.committed is True
    compiled = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
    )
    assert "INSERT INTO agent_workflows" in compiled
    assert "INSERT INTO agent_workflow_runs" in compiled


async def test_langgraph_workflow_store_pauses_run_by_checkpoint_ref() -> None:
    run_id = uuid4()
    workflow_id = uuid4()
    program_id = uuid4()
    correlation_id = uuid4()
    wait_condition_id = uuid4()
    session = FakeSession(
        [
            {
                "workflow_id": workflow_id,
                "run_id": run_id,
                "program_id": program_id,
                "campaign_id": None,
                "correlation_id": correlation_id,
                "workflow_type": "surface_hypothesis",
                "status": "waiting",
                "current_node": "wait_for_projections",
                "checkpoint_ref": "pg-checkpoint:run",
                "metadata": {
                    "action_ids": [],
                    "wait_condition_ids": [str(wait_condition_id)],
                    "result_set_keys": [],
                },
            }
        ]
    )
    store = LangGraphWorkflowStore(FakeSessionFactory(session))

    state = await store.pause_run(
        run_id=run_id,
        checkpoint_ref="pg-checkpoint:run",
        current_node="wait_for_projections",
        wait_condition_id=wait_condition_id,
    )

    assert state.status == "waiting"
    assert state.checkpoint_ref == "pg-checkpoint:run"
    compiled = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
    )
    assert "UPDATE agent_workflow_runs" in compiled
    assert "status=%(status)s" in compiled
    assert "checkpoint_ref" in compiled


async def test_langgraph_workflow_store_cancels_run_without_new_schema() -> None:
    run_id = uuid4()
    workflow_id = uuid4()
    program_id = uuid4()
    correlation_id = uuid4()
    session = FakeSession(
        [
            {
                "workflow_id": workflow_id,
                "run_id": run_id,
                "program_id": program_id,
                "campaign_id": None,
                "correlation_id": correlation_id,
                "workflow_type": "surface_hypothesis",
                "status": "cancelled",
                "current_node": "approval",
                "checkpoint_ref": "pg-checkpoint:approval",
                "metadata": {
                    "action_ids": [],
                    "wait_condition_ids": [],
                    "result_set_keys": [],
                    "terminal_reason": "human rejected action",
                },
            }
        ]
    )
    store = LangGraphWorkflowStore(FakeSessionFactory(session))

    state = await store.cancel_run(
        run_id=run_id,
        reason="human rejected action",
    )

    assert state.status == "cancelled"
    compiled = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
    )
    assert "UPDATE agent_workflow_runs" in compiled
    assert "UPDATE agent_workflows" in compiled
    assert "finished_at" in compiled
