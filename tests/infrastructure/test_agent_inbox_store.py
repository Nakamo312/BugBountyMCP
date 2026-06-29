from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.infrastructure.agent_coordination import AgentInboxMessage, AgentInboxStore


class FakeResult:
    def scalar_one_or_none(self):
        return uuid4()


class FakeSession:
    def __init__(self) -> None:
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult()

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_agent_inbox_store_enqueues_messages_idempotently_by_dedupe_key() -> None:
    session = FakeSession()
    store = AgentInboxStore(FakeSessionFactory(session))

    await store.enqueue_once(
        AgentInboxMessage(
            program_id=uuid4(),
            message_type="run.completed",
            payload={"run_id": str(uuid4())},
            dedupe_key="event:abc:subscription:def",
            campaign_id=uuid4(),
            correlation_id=uuid4(),
            event_id=uuid4(),
            workflow_id=uuid4(),
            workflow_run_id=uuid4(),
            subscription_id=uuid4(),
        )
    )

    assert session.committed is True
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO agent_inbox" in compiled
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in compiled
    assert "RETURNING agent_inbox.id" in compiled
