"""Legacy local processor for agent-task inbox handoff messages."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from api.application.agent_action_proposals import AgentActionProposalWriter
from api.application.agent.task.inbox.models import (
    AgentTaskInboxBridgeResult,
    AgentTaskInboxProcessorSweep,
    AgentTaskInboxStore,
)
from api.application.agent.task.inbox.payload import error_summary
from api.application.agent_task_runtime_contracts import AgentTaskRuntime, BoundedAgentTaskRuntime
from api.application.agent_tasks import AGENT_TASK_PROMPT_MESSAGE_TYPE, AgentTaskService


logger = logging.getLogger(__name__)


class AgentTaskInboxProcessor:
    """Legacy local processor for tests/dev; do not autostart in FastAPI."""

    def __init__(
        self,
        *,
        container: Any,
        inbox_store: AgentTaskInboxStore,
        runtime: AgentTaskRuntime | None = None,
        proposal_writer: AgentActionProposalWriter | None = None,
        consumer_id: str = "agent-task-inbox-worker",
        claim_limit: int = 20,
        lease_seconds: int = 300,
        sweep_interval_seconds: float = 2.0,
        program_id: Any | None = None,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        task_service_dependency: Any | None = None,
    ) -> None:
        if not consumer_id.strip():
            raise ValueError("consumer_id must not be empty")
        self.container = container
        self.inbox_store = inbox_store
        self.runtime = runtime or BoundedAgentTaskRuntime()
        self.proposal_writer = proposal_writer
        self.consumer_id = consumer_id
        self.claim_limit = max(1, min(int(claim_limit), 500))
        self.lease_seconds = max(1, int(lease_seconds))
        self.sweep_interval_seconds = max(0.05, float(sweep_interval_seconds))
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.correlation_id = correlation_id
        self.task_service_dependency = task_service_dependency
        self._stop_event = asyncio.Event()
        self._run_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._run_task = asyncio.create_task(self.run(), name="agent-task-inbox-processor")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._run_task is not None:
            self._run_task.cancel()
            await asyncio.gather(self._run_task, return_exceptions=True)
        self._run_task = None

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_once_summary()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent task inbox sweep failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sweep_interval_seconds,
                )
            except TimeoutError:
                pass

    async def process_once(self) -> int:
        return (await self.process_once_summary()).processed

    async def process_once_summary(self) -> AgentTaskInboxProcessorSweep:
        messages = await self.inbox_store.claim_inbox(
            program_id=self.program_id,
            campaign_id=self.campaign_id,
            correlation_id=self.correlation_id,
            message_type=AGENT_TASK_PROMPT_MESSAGE_TYPE,
            consumer_id=self.consumer_id,
            lease_seconds=self.lease_seconds,
            limit=self.claim_limit,
        )
        summary = AgentTaskInboxProcessorSweep(claimed=len(messages))
        for message in messages:
            try:
                result = await self._handoff_message(message)
                summary = summary.with_result(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("agent task inbox handoff failed for message %s", message.get("id"))
                await self._record_handoff_error(message, exc)
                summary = summary.with_failure()
        self._log_sweep_summary(summary)
        return summary

    async def _handoff_message(self, message: dict[str, Any]) -> AgentTaskInboxBridgeResult:
        from api.application.agent.task.inbox import AgentTaskInboxBridge

        async with self.container() as request_container:
            task_service = await request_container.get(self._task_service_dependency())
            bridge = AgentTaskInboxBridge(
                runtime=self.runtime,
                task_service=task_service,
                inbox_store=self.inbox_store,
                proposal_writer=self.proposal_writer,
            )
            return await bridge.handoff(message)

    def _task_service_dependency(self) -> Any:
        return self.task_service_dependency or AgentTaskService

    async def _record_handoff_error(self, message: dict[str, Any], exc: Exception) -> None:
        message_id = message.get("id")
        if message_id is None:
            return
        try:
            await self.inbox_store.record_inbox_handoff_error(
                message_id=message_id,
                error=error_summary(exc),
            )
        except Exception:
            logger.exception(
                "failed to record agent task inbox handoff error for message %s",
                message_id,
            )

    def _log_sweep_summary(self, summary: AgentTaskInboxProcessorSweep) -> None:
        log_level = logging.INFO if summary.claimed or summary.failed else logging.DEBUG
        logger.log(
            log_level,
            "agent task inbox sweep completed",
            extra={
                "agent_task_inbox_consumer_id": self.consumer_id,
                **{f"agent_task_inbox_{key}": value for key, value in summary.log_fields().items()},
            },
        )
