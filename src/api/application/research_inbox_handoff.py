"""Idempotent handoff from claimed research inbox messages into the graph."""
from __future__ import annotations

from typing import Any

from api.application.projections import ProjectionKey
from api.application.research_inbox_models import (
    AgentInboxAckStore,
    AgentWorkflowRunStatusReader,
    ResearchExecutionGraph,
    ResearchInboxBridgeResult,
)
from api.application.research_inbox_payload import (
    _required_uuid,
    hypothesis_request_from_inbox_message,
    research_thread_id_for_inbox_message,
)


class ResearchInboxBridge:
    """Hand a claimed inbox message to the research control graph exactly once.

    A claimed inbox message is not a LangGraph retry queue. It is a delivery
    boundary. The thread id is deterministic, so a re-claimed message resumes or
    acknowledges an already-persisted thread instead of starting a duplicate.
    """

    def __init__(
        self,
        *,
        graph: ResearchExecutionGraph,
        inbox_store: AgentInboxAckStore,
        required_projections: tuple[ProjectionKey, ...] = (),
        workflow_state_reader: AgentWorkflowRunStatusReader | None = None,
    ) -> None:
        self.graph = graph
        self.inbox_store = inbox_store
        self.required_projections = required_projections
        self.workflow_state_reader = workflow_state_reader

    async def handoff(
        self,
        message: dict[str, Any],
    ) -> ResearchInboxBridgeResult:
        message_id = _required_uuid(message, "id")
        thread_id = research_thread_id_for_inbox_message(message)

        workflow_run_id = message.get("workflow_run_id")
        if workflow_run_id is not None:
            status = await self._workflow_run_status(workflow_run_id)
            if terminal_workflow_status(status):
                await self.inbox_store.ack_inbox_message(message_id=message_id)
                return ResearchInboxBridgeResult(
                    message_id=message_id,
                    thread_id=thread_id,
                    outcome="skipped_terminal_workflow",
                    acknowledged=True,
                    graph_result=None,
                    action="ack_without_resume",
                    reason_code=f"workflow_{status}",
                    workflow_status=status,
                )
            graph_result = await self.graph.aresume(thread_id=thread_id)
            outcome = "resumed"
            action = "resume_graph"
        elif await self._thread_has_checkpoint(thread_id):
            graph_result = None
            outcome = "already_started"
            action = "ack_existing_checkpoint"
        else:
            graph_result = await self.graph.ainvoke(
                hypothesis_request_from_inbox_message(message),
                thread_id=thread_id,
                required_projections=self.required_projections,
            )
            outcome = "started"
            action = "start_graph"

        await self.inbox_store.ack_inbox_message(message_id=message_id)
        return ResearchInboxBridgeResult(
            message_id=message_id,
            thread_id=thread_id,
            outcome=outcome,
            acknowledged=True,
            graph_result=graph_result,
            action=action,
            reason_code=None,
            workflow_status=None,
        )

    async def _thread_has_checkpoint(self, thread_id: str) -> bool:
        snapshot = await self.graph.aget_state(thread_id=thread_id)
        values = getattr(snapshot, "values", None)
        return bool(values)

    async def _workflow_run_status(self, run_id: Any) -> str | None:
        if self.workflow_state_reader is None:
            return None
        return await self.workflow_state_reader.get_workflow_run_status(run_id=run_id)


def terminal_workflow_status(status: str | None) -> bool:
    return status in {"completed", "failed", "cancelled"}
