from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.cypher_gateway import (
    CypherAccessDenied,
    CypherGateway,
    CypherGatewayRequest,
    CypherPolicyError,
)


class RecordingExecutor:
    def __init__(self, rows=None) -> None:
        self.rows = rows or [{"node": {"id": "n1"}}]
        self.calls = []

    async def execute_read(self, *, query, parameters, timeout_seconds):
        self.calls.append((query, parameters, timeout_seconds))
        return self.rows


class RecordingAuditStore:
    def __init__(self) -> None:
        self.audit_id = uuid4()
        self.records = []

    async def record_query(self, **kwargs):
        self.records.append(kwargs)
        return self.audit_id


async def test_cypher_gateway_executes_read_query_with_program_boundary_limit_timeout_and_audit() -> None:
    program_id = uuid4()
    executor = RecordingExecutor()
    audit = RecordingAuditStore()
    gateway = CypherGateway(executor=executor, audit_store=audit)

    result = await gateway.execute(
        CypherGatewayRequest(
            program_id=program_id,
            query="MATCH (n {program_id: $program_id}) RETURN n",
            parameters={"program_id": "attacker-controlled"},
            limit=500,
            timeout_seconds=99,
            actor="admin",
            workflow_id=uuid4(),
            debug_approved=True,
        )
    )

    assert result.rows == ({"node": {"id": "n1"}},)
    assert result.limit == 100
    assert result.timeout_seconds == 3.0
    query, parameters, timeout = executor.calls[0]
    assert query.startswith("CALL {\nMATCH")
    assert query.endswith("\nRETURN *\nLIMIT $limit")
    assert parameters["program_id"] == str(program_id)
    assert parameters["limit"] == 100
    assert timeout == 3.0
    assert audit.records[0]["program_id"] == program_id
    assert audit.records[0]["allowed"] is True
    assert audit.records[0]["row_count"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
        "MERGE (n:Host {program_id: $program_id}) RETURN n",
        "MATCH (n) SET n.x = 1 RETURN n",
        "CALL db.labels()",
        "LOAD CSV FROM 'file:///x' AS row RETURN row",
    ],
)
async def test_cypher_gateway_blocks_write_clauses_and_calls(query: str) -> None:
    gateway = CypherGateway(executor=RecordingExecutor(), audit_store=RecordingAuditStore())

    with pytest.raises(CypherPolicyError):
        await gateway.execute(
            CypherGatewayRequest(
                program_id=uuid4(),
                query=query,
                parameters={"program_id": "p"},
                actor="admin",
                debug_approved=True,
            )
        )


async def test_cypher_gateway_requires_program_id_parameter_reference() -> None:
    gateway = CypherGateway(executor=RecordingExecutor(), audit_store=RecordingAuditStore())

    with pytest.raises(CypherPolicyError, match="program_id"):
        await gateway.execute(
            CypherGatewayRequest(
                program_id=uuid4(),
                query="MATCH (n) RETURN n",
                actor="admin",
                debug_approved=True,
            )
        )


async def test_cypher_gateway_denies_default_api_actor_without_debug_approval() -> None:
    audit = RecordingAuditStore()
    gateway = CypherGateway(executor=RecordingExecutor(), audit_store=audit)

    with pytest.raises(CypherAccessDenied, match="admin/debug"):
        await gateway.execute(
            CypherGatewayRequest(
                program_id=uuid4(),
                query="MATCH (n {program_id: $program_id}) RETURN n",
            )
        )

    assert audit.records[0]["allowed"] is False
    assert "registered templates" in audit.records[0]["reason"]


async def test_cypher_gateway_denies_langgraph_actor_even_with_debug_flag() -> None:
    gateway = CypherGateway(executor=RecordingExecutor(), audit_store=RecordingAuditStore())

    with pytest.raises(CypherAccessDenied):
        await gateway.execute(
            CypherGatewayRequest(
                program_id=uuid4(),
                query="MATCH (n {program_id: $program_id}) RETURN n",
                actor="langgraph",
                debug_approved=True,
            )
        )
