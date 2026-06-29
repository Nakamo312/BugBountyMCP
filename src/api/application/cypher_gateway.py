"""Read-only Cypher Gateway application policy."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


_WRITE_OR_UNSAFE_RE = re.compile(
    r"\b(CALL|CREATE|DELETE|DETACH|DROP|LOAD\s+CSV|MERGE|REMOVE|SET)\b",
    re.IGNORECASE,
)


class CypherPolicyError(ValueError):
    pass


class CypherAccessDenied(PermissionError):
    pass


_DEBUG_ACTORS = frozenset({"admin", "operator", "debug"})


@dataclass(frozen=True, slots=True)
class CypherGatewayRequest:
    program_id: UUID
    query: str
    parameters: dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    timeout_seconds: float = 3.0
    actor: str = "api"
    workflow_id: UUID | None = None
    debug_approved: bool = False


@dataclass(frozen=True, slots=True)
class CypherGatewayResult:
    rows: tuple[dict[str, Any], ...]
    audit_id: UUID
    limit: int
    timeout_seconds: float


class CypherReadExecutor(Protocol):
    async def execute_read(
        self,
        *,
        query: str,
        parameters: dict[str, Any],
        timeout_seconds: float,
    ) -> list[dict[str, Any]]: ...


class CypherAuditStore(Protocol):
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
    ) -> UUID: ...


class CypherGateway:
    def __init__(
        self,
        *,
        executor: CypherReadExecutor,
        audit_store: CypherAuditStore,
    ) -> None:
        self.executor = executor
        self.audit_store = audit_store

    async def execute(self, request: CypherGatewayRequest) -> CypherGatewayResult:
        limit = self._limit(request.limit)
        timeout_seconds = self._timeout(request.timeout_seconds)
        parameters = {
            **dict(request.parameters),
            "program_id": str(request.program_id),
            "limit": limit,
        }

        try:
            self._authorize_debug_access(request)
            safe_query = self._safe_query(request.query)
        except (CypherAccessDenied, CypherPolicyError) as exc:
            await self.audit_store.record_query(
                program_id=request.program_id,
                workflow_id=request.workflow_id,
                actor=request.actor,
                query=request.query,
                parameters=parameters,
                allowed=False,
                reason=str(exc),
                row_count=0,
                timeout_seconds=timeout_seconds,
            )
            raise

        bounded_query = f"CALL {{\n{safe_query}\n}}\nRETURN *\nLIMIT $limit"
        rows = await self.executor.execute_read(
            query=bounded_query,
            parameters=parameters,
            timeout_seconds=timeout_seconds,
        )
        audit_id = await self.audit_store.record_query(
            program_id=request.program_id,
            workflow_id=request.workflow_id,
            actor=request.actor,
            query=safe_query,
            parameters=parameters,
            allowed=True,
            reason=None,
            row_count=len(rows),
            timeout_seconds=timeout_seconds,
        )
        return CypherGatewayResult(
            rows=tuple(dict(row) for row in rows),
            audit_id=audit_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _authorize_debug_access(request: CypherGatewayRequest) -> None:
        actor = request.actor.strip().lower()
        if not request.debug_approved or actor not in _DEBUG_ACTORS:
            raise CypherAccessDenied(
                "ad-hoc Cypher is restricted to explicit admin/debug use; "
                "agent and runtime graph access must use registered templates"
            )

    @staticmethod
    def _safe_query(query: str) -> str:
        stripped = query.strip().rstrip(";")
        if not stripped:
            raise CypherPolicyError("query must not be empty")
        if _WRITE_OR_UNSAFE_RE.search(stripped):
            raise CypherPolicyError("cypher gateway allows read-only MATCH/RETURN queries only")
        if "$program_id" not in stripped:
            raise CypherPolicyError("cypher query must reference $program_id")
        return stripped

    @staticmethod
    def _limit(limit: int) -> int:
        return max(1, min(int(limit), 100))

    @staticmethod
    def _timeout(timeout_seconds: float) -> float:
        return max(0.1, min(float(timeout_seconds), 3.0))
