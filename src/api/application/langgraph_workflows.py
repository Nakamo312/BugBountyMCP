"""LangGraph workflow runtime skeleton.

This module owns semantic workflow state only. Tool execution still goes
through ActionService/agent protocol boundaries; workflow state stores stable
IDs and pointers, not raw artifact or HTTP bodies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkflowStartRequest:
    program_id: UUID
    workflow_type: str
    entry_node: str
    campaign_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class LangGraphWorkflowState:
    workflow_id: UUID
    run_id: UUID
    program_id: UUID
    campaign_id: UUID | None
    correlation_id: UUID
    workflow_type: str
    status: str
    current_node: str | None
    checkpoint_ref: str | None
    action_ids: tuple[UUID, ...] = field(default_factory=tuple)
    wait_condition_ids: tuple[UUID, ...] = field(default_factory=tuple)
    result_set_keys: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "program_id": self.program_id,
            "campaign_id": self.campaign_id,
            "correlation_id": self.correlation_id,
            "workflow_type": self.workflow_type,
            "status": self.status,
            "current_node": self.current_node,
            "checkpoint_ref": self.checkpoint_ref,
            "action_ids": self.action_ids,
            "wait_condition_ids": self.wait_condition_ids,
            "result_set_keys": self.result_set_keys,
        }


class LangGraphWorkflowRepository(Protocol):
    async def start_run(self, request: WorkflowStartRequest) -> LangGraphWorkflowState: ...

    async def pause_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str,
        current_node: str,
        wait_condition_id: UUID | None,
    ) -> LangGraphWorkflowState: ...

    async def resume_run(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str | None = None,
    ) -> LangGraphWorkflowState: ...

    async def cancel_run(
        self,
        *,
        run_id: UUID,
        reason: str | None = None,
    ) -> LangGraphWorkflowState: ...


class LangGraphWorkflowRuntime:
    def __init__(self, store: LangGraphWorkflowRepository) -> None:
        self.store = store

    async def start(self, request: WorkflowStartRequest) -> LangGraphWorkflowState:
        return await self.store.start_run(request)

    async def pause(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str,
        current_node: str,
        wait_condition_id: UUID | None = None,
    ) -> LangGraphWorkflowState:
        return await self.store.pause_run(
            run_id=run_id,
            checkpoint_ref=checkpoint_ref,
            current_node=current_node,
            wait_condition_id=wait_condition_id,
        )

    async def resume(
        self,
        *,
        run_id: UUID,
        checkpoint_ref: str | None = None,
    ) -> LangGraphWorkflowState:
        return await self.store.resume_run(
            run_id=run_id,
            checkpoint_ref=checkpoint_ref,
        )

    async def cancel(
        self,
        *,
        run_id: UUID,
        reason: str | None = None,
    ) -> LangGraphWorkflowState:
        return await self.store.cancel_run(
            run_id=run_id,
            reason=reason,
        )
