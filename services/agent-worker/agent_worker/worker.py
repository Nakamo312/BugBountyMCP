from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from api.application.agent.task.inbox import (
    AgentTaskRuntime,
    AgentTaskRuntimeResult,
    runtime_request_from_agent_task_message,
)

from agent_worker.client import AgentControlPlaneClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentWorkerSweep:
    claimed: int = 0
    processed: int = 0
    failed: int = 0


class LangGraphAgentTaskWorker:
    """External worker that bridges agent inbox handoffs to LangGraph runtime."""

    def __init__(
        self,
        *,
        client: AgentControlPlaneClient,
        runtime: AgentTaskRuntime,
        program_id: UUID,
        consumer_id: str,
        claim_limit: int = 10,
        lease_seconds: int = 300,
        campaign_id: UUID | None = None,
    ) -> None:
        self.client = client
        self.runtime = runtime
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.consumer_id = consumer_id
        self.claim_limit = max(1, min(int(claim_limit), 500))
        self.lease_seconds = max(1, int(lease_seconds))

    async def process_once(self) -> AgentWorkerSweep:
        messages = await self.client.claim_agent_task_messages(
            program_id=self.program_id,
            campaign_id=self.campaign_id,
            consumer_id=self.consumer_id,
            lease_seconds=self.lease_seconds,
            limit=self.claim_limit,
        )
        processed = 0
        failed = 0
        for message in messages:
            try:
                await self._process_message(message)
                processed += 1
            except Exception:
                failed += 1
                logger.exception("agent task worker failed to process message %s", message.get("id"))
        return AgentWorkerSweep(claimed=len(messages), processed=processed, failed=failed)

    async def _process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        request = runtime_request_from_agent_task_message(message)
        result = await self.runtime.handle(request)
        payload = _runtime_result_payload(message=message, request=request, result=result)
        return await self.client.ingest_runtime_result(payload)

    async def run_forever(self, *, poll_seconds: float = 2.0) -> None:
        bounded_poll = max(0.1, float(poll_seconds))
        while True:
            sweep = await self.process_once()
            logger.info(
                "agent task worker sweep completed",
                extra={
                    "agent_worker_claimed": sweep.claimed,
                    "agent_worker_processed": sweep.processed,
                    "agent_worker_failed": sweep.failed,
                },
            )
            await asyncio.sleep(bounded_poll)


def _runtime_result_payload(
    *,
    message: dict[str, Any],
    request,
    result: AgentTaskRuntimeResult,
) -> dict[str, Any]:
    return {
        "task_id": str(request.task_id),
        "source_message_id": str(request.message_id),
        "program_id": str(request.program_id),
        "campaign_id": str(request.campaign_id) if request.campaign_id else None,
        "inbox_message_id": str(message.get("id")) if message.get("id") else None,
        "agent_key": result.agent_key,
        "body": result.body,
        "message_kind": result.message_kind.value,
        "status": result.status.value if result.status else None,
        "source": "langgraph-agent-worker",
        "artifact_refs": list(result.artifact_refs),
        "fact_refs": list(result.fact_refs),
        "graph_refs": list(result.graph_refs),
        "action_refs": list(result.action_refs),
        "proposal_refs": list(result.proposal_refs),
        "decision_refs": list(result.decision_refs),
        "proposal_drafts": [draft.model_dump(mode="json") for draft in result.proposal_drafts],
        "metadata": {
            **dict(result.metadata),
            "worker": {
                "name": "langgraph-agent-task-worker",
                "consumer_id": message.get("locked_by"),
                "inbox_message_id": str(message.get("id")) if message.get("id") else None,
            },
        },
        "ack_inbox": True,
    }
