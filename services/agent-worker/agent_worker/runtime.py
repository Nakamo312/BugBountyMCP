from __future__ import annotations

from typing import Any

from api.application.agent.task.inbox import AgentTaskRuntimeRequest
from api.application.langgraph.task.agent.factory import AgentTaskRuntimeFactory
from api.application.langgraph.task.agent.models import AgentTaskContextReader

from agent_worker.client import AgentControlPlaneClient
from agent_worker.settings import AgentWorkerSettings


class ApiAgentTaskContextReader(AgentTaskContextReader):
    """Read compact domain context through the API read-model boundary."""

    def __init__(self, client: AgentControlPlaneClient) -> None:
        self.client = client

    async def read(self, request: AgentTaskRuntimeRequest) -> dict[str, Any]:
        try:
            detail = await self.client.read_task_detail(request.task_id)
        except Exception as exc:
            return {
                "task_id": str(request.task_id),
                "program_id": str(request.program_id),
                "campaign_id": str(request.campaign_id) if request.campaign_id else None,
                "context_refs": list(request.context_refs),
                "metadata_keys": sorted(str(key) for key in request.metadata.keys())[:25],
                "context_error": f"{type(exc).__name__}: {exc}"[:500],
                "raw_artifact_access": "forbidden",
            }
        return {
            "task_id": str(request.task_id),
            "program_id": str(request.program_id),
            "campaign_id": str(request.campaign_id) if request.campaign_id else None,
            "context_refs": list(request.context_refs),
            "task": detail.get("task"),
            "compact_context": detail.get("compact_context") or {},
            "counts": detail.get("counts") or {},
            "recent_message_count": len(detail.get("messages") or []),
            "proposal_count": len(detail.get("proposals") or []),
            "accepted_action_count": len(detail.get("accepted_actions") or []),
            "related_outcome_count": len(detail.get("related_outcomes") or []),
            "raw_artifact_access": "forbidden",
        }


def build_agent_task_runtime(
    *,
    settings: AgentWorkerSettings,
    client: AgentControlPlaneClient,
):
    return AgentTaskRuntimeFactory(
        runtime_name=settings.AGENT_WORKER_RUNTIME,
        default_budget_mode=settings.AGENT_TASK_RUNTIME_DEFAULT_MODE,
        allow_deep_budget_mode=settings.AGENT_TASK_RUNTIME_ALLOW_DEEP,
        require_deep_confirmation=settings.AGENT_TASK_RUNTIME_REQUIRE_DEEP_CONFIRMATION,
        deep_allowed_actors=settings.AGENT_TASK_RUNTIME_DEEP_ALLOWED_ACTORS,
        langgraph_checkpoint_ns=settings.AGENT_TASK_LANGGRAPH_CHECKPOINT_NS,
        context_reader=ApiAgentTaskContextReader(client),
    ).create()
