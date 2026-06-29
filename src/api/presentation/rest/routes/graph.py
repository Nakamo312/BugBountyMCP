from __future__ import annotations

from typing import Any
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.application.cypher_gateway import (
    CypherGateway,
    CypherAccessDenied,
    CypherGatewayRequest,
    CypherPolicyError,
)


router = APIRouter(route_class=DishkaRoute)


class CypherQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    query: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=100)
    timeout_seconds: float = Field(default=3.0, gt=0, le=3.0)
    actor: str = Field(default="api", min_length=1, max_length=100)
    workflow_id: UUID | None = None
    debug_approved: bool = False


@router.post("/cypher")
async def execute_debug_cypher(
    request: CypherQueryRequest,
    gateway: FromDishka[CypherGateway],
) -> dict[str, Any]:
    try:
        result = await gateway.execute(CypherGatewayRequest(**request.model_dump()))
    except CypherAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CypherPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "audit_id": result.audit_id,
        "rows": result.rows,
        "limit": result.limit,
        "timeout_seconds": result.timeout_seconds,
    }
