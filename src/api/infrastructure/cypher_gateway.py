"""Infrastructure adapters for the read-only Cypher Gateway."""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert

from api.infrastructure.adapters.orm import cypher_query_audits


class CypherGatewayAuditStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def record_query(
        self,
        *,
        program_id: UUID,
        workflow_id: UUID | None,
        actor: str,
        query: str,
        parameters: dict[str, Any],
        allowed: bool,
        reason: str | None,
        row_count: int,
        timeout_seconds: float,
    ) -> UUID:
        statement = (
            insert(cypher_query_audits)
            .values(
                id=uuid4(),
                program_id=program_id,
                workflow_id=workflow_id,
                actor=actor,
                query_hash=self._hash(query),
                params_hash=self._hash(parameters),
                allowed=allowed,
                reason=reason,
                row_count=row_count,
                timeout_seconds=timeout_seconds,
            )
            .returning(cypher_query_audits.c.id)
        )
        async with self.session_factory() as session:
            result = await session.execute(statement)
            audit_id = result.scalar_one()
            await session.commit()
        return audit_id

    @staticmethod
    def _hash(value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Neo4jReadExecutor:
    def __init__(self, driver) -> None:
        self.driver = driver

    async def execute_read(
        self,
        *,
        query: str,
        parameters: dict[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        # Neo4j Python driver is sync in the graph-projector stack; keep this
        # adapter tiny and isolated so application code never imports it.
        import asyncio

        return await asyncio.to_thread(
            self._execute_read_sync,
            query=query,
            parameters=parameters,
            timeout_seconds=timeout_seconds,
        )

    def _execute_read_sync(
        self,
        *,
        query: str,
        parameters: dict[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        from neo4j import Query

        with self.driver.session(default_access_mode="READ") as session:
            result = session.run(
                Query(query, timeout=timeout_seconds),
                parameters,
            )
            return [dict(record) for record in result]
