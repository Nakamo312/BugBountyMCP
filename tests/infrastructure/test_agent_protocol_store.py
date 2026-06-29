from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.infrastructure.agent_coordination import AgentProtocolStore


class FakeResult:
    def __init__(self, rows=None, scalar=None, rowcount=0) -> None:
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, rows=None, scalar=None, rowcount=0) -> None:
        self.rows = rows or []
        self.scalar = scalar
        self.rowcount = rowcount
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.rows, self.scalar, self.rowcount)

    async def commit(self) -> None:
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


async def test_agent_protocol_store_creates_subscription_idempotently() -> None:
    subscription_id = uuid4()
    session = FakeSession(scalar=subscription_id)
    store = AgentProtocolStore(FakeSessionFactory(session))

    created = await store.create_subscription(
        program_id=uuid4(),
        event_type="run.completed",
        inbox_key="mvp-hypothesis-builder",
        dedupe_key="program:event:consumer",
        campaign_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert created == subscription_id
    assert session.committed is True
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO agent_subscriptions" in compiled
    assert "ON CONFLICT (dedupe_key) DO UPDATE" in compiled
    assert "RETURNING agent_subscriptions.id" in compiled


async def test_agent_protocol_store_claims_inbox_with_lease_and_skip_locked() -> None:
    message_id = uuid4()
    program_id = uuid4()
    session = FakeSession(
        rows=[{"id": message_id, "program_id": program_id, "status": "claimed"}]
    )
    store = AgentProtocolStore(FakeSessionFactory(session))

    claimed = await store.claim_inbox(
        program_id=program_id,
        consumer_id="agent-worker-1",
        lease_seconds=120,
        limit=10,
    )

    assert claimed == [{"id": message_id, "program_id": program_id, "status": "claimed"}]
    assert session.committed is True
    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    compiled = str(compiled_statement)
    assert "WITH claimable_agent_inbox AS" in compiled
    assert "FOR UPDATE SKIP LOCKED" in compiled
    assert "UPDATE agent_inbox" in compiled
    assert "RETURNING agent_inbox.id" in compiled
    assert compiled_statement.params["status"] == "claimed"
    assert compiled_statement.params["locked_by"] == "agent-worker-1"


async def test_agent_protocol_store_claims_inbox_by_subscription_inbox_key() -> None:
    message_id = uuid4()
    session = FakeSession(rows=[{"id": message_id, "status": "claimed"}])
    store = AgentProtocolStore(FakeSessionFactory(session))

    claimed = await store.claim_inbox(
        program_id=None,
        consumer_id="mvp-research-worker",
        inbox_key="mvp-hypothesis-builder",
        limit=5,
    )

    assert claimed == [{"id": message_id, "status": "claimed"}]
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "JOIN agent_subscriptions" in compiled
    assert "agent_subscriptions.inbox_key" in compiled
    assert "FOR UPDATE SKIP LOCKED" in compiled


async def test_agent_protocol_store_rejects_empty_inbox_consumer_id() -> None:
    store = AgentProtocolStore(FakeSessionFactory(FakeSession()))

    try:
        await store.claim_inbox(program_id=uuid4(), consumer_id="   ")
    except ValueError as exc:
        assert "consumer_id" in str(exc)
    else:
        raise AssertionError("empty consumer_id should be rejected")


async def test_agent_protocol_store_acks_inbox_only_from_claimable_statuses() -> None:
    session = FakeSession()
    store = AgentProtocolStore(FakeSessionFactory(session))

    await store.ack_inbox_message(message_id=uuid4())

    assert session.committed is True
    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    compiled = str(compiled_statement)
    assert "UPDATE agent_inbox" in compiled
    assert compiled_statement.params["status"] == "processed"
    assert "agent_inbox.status IN" in compiled
    assert "processed_at" in compiled


async def test_agent_protocol_store_records_inbox_handoff_error_without_releasing_lease() -> None:
    message_id = uuid4()
    session = FakeSession()
    store = AgentProtocolStore(FakeSessionFactory(session))

    await store.record_inbox_handoff_error(
        message_id=message_id,
        error="RuntimeError: graph unavailable",
    )

    assert session.committed is True
    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    compiled = str(compiled_statement)
    assert "UPDATE agent_inbox" in compiled
    assert "agent_inbox.status =" in compiled
    assert "locked_by" not in compiled
    assert "locked_until" not in compiled
    assert compiled_statement.params["status_1"] == "claimed"
    assert compiled_statement.params["last_error"] == "RuntimeError: graph unavailable"


async def test_agent_protocol_store_truncates_inbox_handoff_error() -> None:
    session = FakeSession()
    store = AgentProtocolStore(FakeSessionFactory(session))

    await store.record_inbox_handoff_error(
        message_id=uuid4(),
        error="x" * 5000,
    )

    compiled_statement = session.statements[0].compile(dialect=postgresql.dialect())
    assert len(compiled_statement.params["last_error"]) == 4000


async def test_agent_protocol_store_upserts_result_sets_by_program_key() -> None:
    result_set_id = uuid4()
    session = FakeSession(scalar=result_set_id)
    store = AgentProtocolStore(FakeSessionFactory(session))

    created = await store.upsert_result_set(
        program_id=uuid4(),
        result_type="surface-context",
        result_key="action:123:surface-context",
        payload={"summary": "bounded"},
        artifact_refs=[{"artifact_id": str(uuid4())}],
        fact_refs=[],
        search_refs=[],
        graph_refs=[],
        action_id=uuid4(),
    )

    assert created == result_set_id
    assert session.committed is True
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO agent_result_sets" in compiled
    assert "ON CONFLICT (program_id, result_key) DO UPDATE" in compiled
    assert "RETURNING agent_result_sets.id" in compiled


async def test_agent_protocol_store_lists_result_sets_by_scope() -> None:
    program_id = uuid4()
    action_id = uuid4()
    session = FakeSession(rows=[{"id": uuid4(), "program_id": program_id, "result_key": "k"}])
    store = AgentProtocolStore(FakeSessionFactory(session))

    rows = await store.list_result_sets(program_id=program_id, action_id=action_id)

    assert rows == [{"id": rows[0]["id"], "program_id": program_id, "result_key": "k"}]
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "agent_result_sets.program_id" in compiled
    assert "agent_result_sets.action_id" in compiled


async def test_agent_protocol_store_reads_workflow_run_status() -> None:
    session = FakeSession(scalar="cancelled")
    store = AgentProtocolStore(FakeSessionFactory(session))

    status = await store.get_workflow_run_status(run_id=uuid4())

    assert status == "cancelled"
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "SELECT agent_workflow_runs.status" in compiled
    assert "agent_workflow_runs.id" in compiled


async def test_agent_protocol_store_cancels_workflow_run_dependents() -> None:
    session = FakeSession(rowcount=1)
    store = AgentProtocolStore(FakeSessionFactory(session))

    result = await store.cancel_workflow_run_dependents(
        run_id=uuid4(),
        reason="operator cancelled",
    )

    assert result == {
        "subscriptions_cancelled": 1,
        "inbox_messages_cancelled": 1,
        "wait_conditions_cancelled": 1,
    }
    assert session.committed is True
    compiled = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
    )
    assert "UPDATE agent_subscriptions" in compiled
    assert "UPDATE agent_inbox" in compiled
    assert "UPDATE agent_wait_conditions" in compiled
    assert "agent_inbox.status IN" in compiled
    assert "agent_wait_conditions.status =" in compiled
    inbox_statement = session.statements[1].compile(dialect=postgresql.dialect())
    assert inbox_statement.params["status"] == "cancelled"
    assert inbox_statement.params["last_error"].startswith("workflow cancelled")
