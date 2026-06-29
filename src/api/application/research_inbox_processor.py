"""Claim-loop worker for research inbox handoff."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from api.application.projections import ProjectionKey
from api.application.research_inbox_handoff import ResearchInboxBridge
from api.application.research_inbox_models import (
    AgentInboxClaimStore,
    ResearchInboxBridgeResult,
    ResearchInboxProcessorSweep,
)
from api.application.research_inbox_payload import error_summary

logger = logging.getLogger("api.application.research_inbox_bridge")


class ResearchInboxProcessor:
    """Claim research inbox messages and hand them off to LangGraph.

    The processor owns only the delivery boundary: claim available messages, open
    a request-scoped graph, perform an idempotent handoff, then ack only after
    the graph has persisted or resumed. LangGraph remains the retry/checkpoint
    runtime after handoff.
    """

    def __init__(
        self,
        *,
        container: Any,
        inbox_store: AgentInboxClaimStore,
        consumer_id: str = "research-inbox-worker",
        inbox_key: str = "research-hypothesis-builder",
        claim_limit: int = 20,
        lease_seconds: int = 300,
        sweep_interval_seconds: float = 2.0,
        program_id: Any | None = None,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        required_projections: tuple[ProjectionKey, ...] = (),
        graph_dependency: Any | None = None,
    ) -> None:
        if not consumer_id.strip():
            raise ValueError("consumer_id must not be empty")
        if not inbox_key.strip():
            raise ValueError("inbox_key must not be empty")
        self.container = container
        self.inbox_store = inbox_store
        self.consumer_id = consumer_id
        self.inbox_key = inbox_key
        self.claim_limit = max(1, min(int(claim_limit), 500))
        self.lease_seconds = max(1, int(lease_seconds))
        self.sweep_interval_seconds = max(0.05, float(sweep_interval_seconds))
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.correlation_id = correlation_id
        self.required_projections = required_projections
        self.graph_dependency = graph_dependency
        self._stop_event = asyncio.Event()
        self._run_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._run_task = asyncio.create_task(
            self.run(),
            name="research-inbox-processor",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._run_task is not None:
            self._run_task.cancel()
            await asyncio.gather(self._run_task, return_exceptions=True)
        self._run_task = None

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("research inbox sweep failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sweep_interval_seconds,
                )
            except TimeoutError:
                pass

    async def process_once(self) -> int:
        """Process one sweep and return the compatibility success count."""

        return (await self.process_once_summary()).processed

    async def process_once_summary(self) -> ResearchInboxProcessorSweep:
        messages = await self.inbox_store.claim_inbox(
            program_id=self.program_id,
            campaign_id=self.campaign_id,
            correlation_id=self.correlation_id,
            inbox_key=self.inbox_key,
            consumer_id=self.consumer_id,
            lease_seconds=self.lease_seconds,
            limit=self.claim_limit,
        )
        summary = ResearchInboxProcessorSweep(claimed=len(messages))
        for message in messages:
            try:
                result = await self._handoff_message(message)
                summary = summary.with_result(result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "research inbox handoff failed for message %s",
                    message.get("id"),
                )
                await self._record_handoff_error(message, exc)
                summary = summary.with_failure()
        self._log_sweep_summary(summary)
        return summary

    def _log_sweep_summary(self, summary: ResearchInboxProcessorSweep) -> None:
        log_level = logging.INFO if summary.claimed or summary.failed else logging.DEBUG
        logger.log(
            log_level,
            "research inbox sweep completed",
            extra={
                "research_inbox_consumer_id": self.consumer_id,
                "research_inbox_key": self.inbox_key,
                **{f"research_inbox_{key}": value for key, value in summary.log_fields().items()},
            },
        )

    async def _record_handoff_error(
        self,
        message: dict[str, Any],
        exc: Exception,
    ) -> None:
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
                "Failed to record research inbox handoff error for message %s",
                message_id,
            )

    def _graph_dependency(self) -> Any:
        if self.graph_dependency is not None:
            return self.graph_dependency
        from api.application.research_control_graph import ResearchControlGraph

        return ResearchControlGraph

    async def _handoff_message(self, message: dict[str, Any]) -> ResearchInboxBridgeResult:
        async with self.container() as request_container:
            graph = await request_container.get(self._graph_dependency())
            handoff = ResearchInboxBridge(
                graph=graph,
                inbox_store=self.inbox_store,
                workflow_state_reader=self.inbox_store,
                required_projections=self.required_projections,
            )
            return await handoff.handoff(message)
