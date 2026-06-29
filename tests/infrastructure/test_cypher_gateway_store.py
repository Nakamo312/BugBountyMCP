from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from api.infrastructure.cypher_gateway import CypherGatewayAuditStore


class FakeResult:
    def __init__(self, scalar):
        self.scalar = scalar

    def scalar_one(self):
        return self.scalar


class FakeSession:
    def __init__(self, scalar):
        self.scalar = scalar
        self.statements = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.scalar)

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


async def test_cypher_gateway_audit_store_records_hashes_not_raw_query() -> None:
    audit_id = uuid4()
    session = FakeSession(audit_id)
    store = CypherGatewayAuditStore(FakeSessionFactory(session))

    recorded = await store.record_query(
        program_id=uuid4(),
        workflow_id=uuid4(),
        actor="langgraph",
        query="MATCH (n {program_id: $program_id}) RETURN n",
        parameters={"program_id": "p"},
        allowed=True,
        reason=None,
        row_count=3,
        timeout_seconds=3.0,
    )

    assert recorded == audit_id
    assert session.committed is True
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "INSERT INTO cypher_query_audits" in sql
    assert "query_hash" in sql
    assert "params_hash" in sql
    assert "RETURNING cypher_query_audits.id" in sql
