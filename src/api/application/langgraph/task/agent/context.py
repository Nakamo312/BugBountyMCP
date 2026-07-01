"""Context readers for the LangGraph-backed agent task runtime."""
from __future__ import annotations

from typing import Any

from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest
from api.application.langgraph.task.agent.helpers import bounded_dicts, optional_uuid_text


class EmptyAgentTaskContextReader:
    """Default context reader that exposes only request pointers and refs."""

    async def read(self, request: AgentTaskRuntimeRequest) -> dict[str, Any]:
        return {
            "program_id": str(request.program_id),
            "campaign_id": optional_uuid_text(request.campaign_id),
            "correlation_id": optional_uuid_text(request.correlation_id),
            "task_id": str(request.task_id),
            "message_id": str(request.message_id),
            "target_agent": request.target_agent,
            "context_refs": bounded_dicts(request.context_refs, limit=25),
            "metadata_keys": sorted(str(key) for key in request.metadata.keys())[:25],
        }
