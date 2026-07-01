"""Infrastructure adapter that resumes research-control graphs through DI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from api.application.agent_wait_conditions import AgentWaitConditionRecord
from api.application.research_control_graph import ResearchControlGraph

TERMINAL_WORKFLOW_STATUSES = frozenset({"completed", "failed", "cancelled"})


class WorkflowRunStatusReader(Protocol):
    async def get_workflow_run_status(self, *, run_id: Any) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ResearchWaitResumeResult:
    status: str
    thread_id: str | None = None
    workflow_status: str | None = None


class ResearchWaitResumer:
    """Continue a research pass after a durable wait condition resolves.

    The wait processor may see old or duplicate wait rows. This adapter keeps
    that boundary safe: it resumes only non-terminal workflow runs and returns a
    small status object for observability. LangGraph still owns graph execution;
    this adapter only performs the handoff.
    """

    def __init__(
        self,
        *,
        container: Any,
        workflow_status_reader: WorkflowRunStatusReader | None = None,
    ) -> None:
        self.container = container
        self.workflow_status_reader = workflow_status_reader

    async def resume(self, record: AgentWaitConditionRecord) -> ResearchWaitResumeResult:
        if record.workflow_run_id is None:
            return ResearchWaitResumeResult(status="missing_workflow_run")

        workflow_status = await self._workflow_status(record.workflow_run_id)
        if workflow_status in TERMINAL_WORKFLOW_STATUSES:
            return ResearchWaitResumeResult(
                status="skipped_terminal_workflow",
                thread_id=str(record.workflow_run_id),
                workflow_status=workflow_status,
            )

        async with self.container() as request_container:
            graph = await request_container.get(ResearchControlGraph)
            await graph.aresume(thread_id=str(record.workflow_run_id))

        return ResearchWaitResumeResult(
            status="resumed",
            thread_id=str(record.workflow_run_id),
            workflow_status=workflow_status,
        )

    async def _workflow_status(self, run_id: Any) -> str | None:
        if self.workflow_status_reader is None:
            return None
        return await self.workflow_status_reader.get_workflow_run_status(run_id=run_id)
