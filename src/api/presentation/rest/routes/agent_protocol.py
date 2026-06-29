from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from api.application.agent_tasks import AgentTaskAgentReplyRequest, AgentTaskService
from api.application.agent_task_runtime_results import (
    AgentTaskRuntimeResultIngestRequest,
    AgentTaskRuntimeResultIngestService,
)
from api.application.langgraph_workflows import LangGraphWorkflowRuntime
from api.infrastructure.agent_coordination import AgentProtocolStore
from api.presentation.rest.security import require_agent_protocol_internal_access


router = APIRouter(
    route_class=DishkaRoute,
    dependencies=[Depends(require_agent_protocol_internal_access)],
)


class AgentSubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    event_type: str = Field(min_length=1, max_length=150)
    inbox_key: str = Field(min_length=1, max_length=200)
    dedupe_key: str = Field(min_length=1, max_length=300)
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentWaitConditionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_run_id: UUID
    program_id: UUID
    condition_type: str = Field(min_length=1, max_length=50)
    condition_key: str = Field(min_length=1, max_length=300)
    required_state: dict[str, Any] = Field(default_factory=dict)
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    deadline_at: datetime | None = None


class AgentResultSetUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    result_type: str = Field(min_length=1, max_length=100)
    result_key: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    fact_refs: list[dict[str, Any]] = Field(default_factory=list)
    search_refs: list[dict[str, Any]] = Field(default_factory=list)
    graph_refs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_id: UUID | None = None
    workflow_run_id: UUID | None = None
    action_id: UUID | None = None
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None


class AgentWorkflowCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=4000)


class AgentInboxClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    consumer_id: str = Field(min_length=1, max_length=100)
    inbox_key: str | None = Field(default=None, min_length=1, max_length=200)
    message_type: str | None = Field(default=None, min_length=1, max_length=150)
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)
    lease_seconds: int = Field(default=300, ge=1, le=3600)


@router.post("/subscriptions", status_code=201)
async def create_subscription(
    request: AgentSubscriptionCreateRequest,
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    subscription_id = await store.create_subscription(**request.model_dump())
    return {"subscription_id": subscription_id}


@router.get("/inbox")
async def list_inbox(
    store: FromDishka[AgentProtocolStore],
    program_id: UUID,
    status: str | None = "pending",
    campaign_id: UUID | None = None,
    correlation_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    items = await store.list_inbox(
        program_id=program_id,
        status=status,
        campaign_id=campaign_id,
        correlation_id=correlation_id,
        limit=limit,
    )
    return {"items": items}


@router.post("/inbox/claim")
async def claim_inbox_messages(
    request: AgentInboxClaimRequest,
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    items = await store.claim_inbox(**request.model_dump())
    return {"items": items}


@router.post("/inbox/{message_id}/ack")
async def ack_inbox_message(
    message_id: UUID,
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    await store.ack_inbox_message(message_id=message_id)
    return {"message_id": message_id, "status": "processed"}


@router.post("/workflows/{run_id}/cancel")
async def cancel_workflow_run(
    run_id: UUID,
    request: AgentWorkflowCancelRequest,
    workflow_runtime: FromDishka[LangGraphWorkflowRuntime],
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    state = await workflow_runtime.cancel(run_id=run_id, reason=request.reason)
    cancelled = await store.cancel_workflow_run_dependents(
        run_id=run_id,
        reason=request.reason,
    )
    return {
        "workflow": state.to_dict(),
        "cancelled": cancelled,
    }


@router.post("/wait-conditions", status_code=201)
async def create_wait_condition(
    request: AgentWaitConditionCreateRequest,
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    condition_id = await store.create_wait_condition(**request.model_dump())
    return {"condition_id": condition_id}


@router.get("/wait-conditions")
async def list_wait_conditions(
    store: FromDishka[AgentProtocolStore],
    program_id: UUID,
    status: str | None = None,
    campaign_id: UUID | None = None,
    correlation_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    items = await store.list_wait_conditions(
        program_id=program_id,
        status=status,
        campaign_id=campaign_id,
        correlation_id=correlation_id,
        limit=limit,
    )
    return {"items": items}


@router.post("/result-sets", status_code=201)
async def upsert_result_set(
    request: AgentResultSetUpsertRequest,
    store: FromDishka[AgentProtocolStore],
) -> dict[str, Any]:
    result_set_id = await store.upsert_result_set(**request.model_dump())
    return {"result_set_id": result_set_id}


@router.get("/result-sets")
async def list_result_sets(
    store: FromDishka[AgentProtocolStore],
    program_id: UUID,
    result_key: str | None = None,
    action_id: UUID | None = None,
    campaign_id: UUID | None = None,
    workflow_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    items = await store.list_result_sets(
        program_id=program_id,
        result_key=result_key,
        action_id=action_id,
        campaign_id=campaign_id,
        workflow_id=workflow_id,
        workflow_run_id=workflow_run_id,
        limit=limit,
    )
    return {"items": items}



@router.post("/task-runtime-results", status_code=201)
async def ingest_agent_task_runtime_result(
    request: AgentTaskRuntimeResultIngestRequest,
    service: FromDishka[AgentTaskRuntimeResultIngestService],
) -> dict[str, Any]:
    """Persist typed output from an internal LangGraph agent-task worker."""

    ingested = await service.ingest(request)
    return ingested.model_dump(mode="json")

@router.post("/tasks/{task_id}/messages", status_code=201)
async def append_agent_task_reply(
    task_id: UUID,
    request: AgentTaskAgentReplyRequest,
    service: FromDishka[AgentTaskService],
) -> dict[str, Any]:
    message = await service.append_agent_reply(
        task_id=task_id,
        request=request,
    )
    return message.model_dump(mode="json")
