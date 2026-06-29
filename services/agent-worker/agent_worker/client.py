from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from api.application.agent_tasks import AGENT_TASK_PROMPT_MESSAGE_TYPE


class AgentControlPlaneClient:
    """HTTP client for the internal agent protocol boundary.

    The worker talks to the API through internal agent-protocol endpoints. It
    claims only agent task prompt/follow-up messages and posts typed runtime
    results back to the domain layer. It never calls action execution endpoints.
    """

    def __init__(
        self,
        *,
        base_url: str,
        actor: str,
        internal_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Agent-Actor": actor}
        if internal_token:
            self.headers["X-Agent-Internal-Token"] = internal_token
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout_seconds,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def claim_agent_task_messages(
        self,
        *,
        program_id: UUID,
        consumer_id: str,
        lease_seconds: int,
        limit: int,
        campaign_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "program_id": str(program_id),
            "consumer_id": consumer_id,
            "lease_seconds": lease_seconds,
            "limit": limit,
            "message_type": AGENT_TASK_PROMPT_MESSAGE_TYPE,
        }
        if campaign_id is not None:
            payload["campaign_id"] = str(campaign_id)
        response = await self.client.post("/api/v1/agent/inbox/claim", json=payload)
        response.raise_for_status()
        return list(response.json().get("items") or [])

    async def ingest_runtime_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.post("/api/v1/agent/task-runtime-results", json=payload)
        response.raise_for_status()
        return dict(response.json())

    async def read_task_detail(self, task_id: UUID) -> dict[str, Any]:
        response = await self.client.get(f"/api/v1/agent-tasks/{task_id}/detail")
        response.raise_for_status()
        return dict(response.json())
