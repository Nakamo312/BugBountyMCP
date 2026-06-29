from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.infrastructure.agent_wait_state import AgentExecutionStateReader


class FakeResult:
    def __init__(self, row) -> None:
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeSession:
    def __init__(self, row) -> None:
        self.row = row
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.row)


class FakeSessionFactory:
    def __init__(self, session) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_execution_state_reader_scopes_run_by_program() -> None:
    program_id = uuid4()
    run_id = uuid4()
    session = FakeSession(
        {
            "id": run_id,
            "status": "completed",
            "terminal_outcome": "completed",
        }
    )
    reader = AgentExecutionStateReader(FakeSessionFactory(session))

    state = await reader.get_run_state(program_id=program_id, run_id=run_id)

    assert state.run_id == run_id
    assert state.status == "completed"
    assert state.terminal_outcome == "completed"
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "FROM runs" in sql
    assert "runs.id = " in sql
    assert "runs.program_id = " in sql
