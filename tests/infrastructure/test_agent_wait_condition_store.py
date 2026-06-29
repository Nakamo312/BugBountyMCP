from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.infrastructure.agent_coordination import AgentWaitConditionStore


class FakeResult:
    def __init__(self, rows=None, rowcount=1) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows=None, rowcount=1) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.rows, self.rowcount)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_agent_wait_condition_store_lists_pending_records_for_processor() -> None:
    condition_id = uuid4()
    program_id = uuid4()
    deadline = datetime.now(timezone.utc)
    session = FakeSession(
        [
            {
                "id": condition_id,
                "condition_key": "mvp-research:projections_ready:abc",
                "condition_type": "projections_ready",
                "program_id": program_id,
                "workflow_run_id": uuid4(),
                "required_state": {"projections": []},
                "deadline_at": deadline,
            }
        ]
    )
    store = AgentWaitConditionStore(FakeSessionFactory(session))

    records = await store.list_pending(limit=25, now=datetime.now(timezone.utc))

    assert len(records) == 1
    assert records[0].condition_id == condition_id
    assert records[0].condition_key == "mvp-research:projections_ready:abc"
    assert records[0].condition_type == "projections_ready"
    assert records[0].program_id == program_id
    assert records[0].required_state == {"projections": []}
    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "agent_wait_conditions.status = " in sql
    assert "ORDER BY agent_wait_conditions.created_at ASC" in sql
    assert "LIMIT " in sql


async def test_agent_wait_condition_store_marks_resolved_only_from_pending() -> None:
    session = FakeSession()
    store = AgentWaitConditionStore(FakeSessionFactory(session))

    changed = await store.mark_resolved(condition_id=uuid4(), payload={"missing": []})

    assert session.committed is True
    assert changed is True
    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    compiled = str(compiled_statement)
    assert "UPDATE agent_wait_conditions" in compiled
    assert compiled_statement.params["status"] == "resolved"
    assert "agent_wait_conditions.status = " in compiled
    assert "resolved_payload" in compiled
    assert "resolved_at" in compiled


async def test_agent_wait_condition_store_reports_lost_terminal_transition() -> None:
    session = FakeSession(rowcount=0)
    store = AgentWaitConditionStore(FakeSessionFactory(session))

    changed = await store.mark_resolved(
        condition_id=uuid4(),
        payload={"result_set_keys": []},
    )

    assert changed is False


async def test_agent_wait_condition_store_lists_resolved_waits_for_waiting_runs() -> None:
    workflow_run_id = uuid4()
    session = FakeSession(
        [
            {
                "id": uuid4(),
                "condition_key": "mvp-research:new_facts_available:retry",
                "condition_type": "new_facts_available",
                "program_id": uuid4(),
                "workflow_run_id": workflow_run_id,
                "required_state": {"result_key": "surface:admin"},
                "deadline_at": None,
            }
        ]
    )
    store = AgentWaitConditionStore(FakeSessionFactory(session))

    records = await store.list_resume_ready(limit=10)

    assert records[0].workflow_run_id == workflow_run_id
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "JOIN agent_workflow_runs" in compiled
    assert "agent_wait_conditions.status = " in compiled
    assert "agent_workflow_runs.status = " in compiled
    assert "DISTINCT ON (agent_wait_conditions.workflow_run_id)" in compiled
    assert "NOT (EXISTS" in compiled


async def test_agent_wait_condition_store_marks_timeout_only_from_pending() -> None:
    session = FakeSession()
    store = AgentWaitConditionStore(FakeSessionFactory(session))

    await store.mark_timed_out(condition_id=uuid4(), payload={"reason": "deadline_elapsed"})

    assert session.committed is True
    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    compiled = str(compiled_statement)
    assert "UPDATE agent_wait_conditions" in compiled
    assert compiled_statement.params["status"] == "timed_out"
    assert "resolved_payload" in compiled
