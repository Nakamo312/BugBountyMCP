"""LangGraph tool for requesting controlled tool actions.

The tool is intentionally thin: it creates the existing ActionRequest contract
and delegates to ActionService. It never publishes transport events, invokes
execution adapters, or writes orchestration state directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4

from api.application.contracts import ActionKind, ActionRequest, ActionSubmission


@dataclass(frozen=True, slots=True)
class LangGraphToolActionRequest:
    program_id: UUID
    catalog_id: UUID
    targets: list[str]
    options: dict[str, Any] = field(default_factory=dict)
    workflow_id: UUID | None = None
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolActionService(Protocol):
    async def request_action(self, request: ActionRequest) -> ActionSubmission: ...


class LangGraphToolActionTool:
    def __init__(self, *, action_service: ToolActionService) -> None:
        self.action_service = action_service

    async def create_action(
        self,
        request: LangGraphToolActionRequest,
    ) -> ActionSubmission:
        action = ActionRequest(
            kind=ActionKind.SCAN,
            program_id=request.program_id,
            catalog_id=request.catalog_id,
            targets=request.targets,
            options=request.options,
            requested_by="langgraph",
            workflow_id=request.workflow_id,
            campaign_id=request.campaign_id or uuid4(),
            correlation_id=request.correlation_id or uuid4(),
            metadata={
                **request.metadata,
                "langgraph_tool": True,
            },
        )
        return await self.action_service.request_action(action)
