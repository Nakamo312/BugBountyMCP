from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentWorkerSettings(BaseSettings):
    """Configuration for the external LangGraph agent-task worker."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CONTROL_API_BASE_URL: str = "http://localhost:8000"
    AGENT_PROTOCOL_INTERNAL_TOKEN: str | None = None
    AGENT_WORKER_ACTOR: str = "agent-worker"
    AGENT_WORKER_CONSUMER_ID: str = "langgraph-agent-task-worker"
    AGENT_WORKER_PROGRAM_ID: str = Field(default="", description="Program UUID to claim")
    AGENT_WORKER_CAMPAIGN_ID: str | None = None
    AGENT_WORKER_CLAIM_LIMIT: int = 10
    AGENT_WORKER_LEASE_SECONDS: int = 300
    AGENT_WORKER_POLL_SECONDS: float = 2.0
    AGENT_WORKER_RUNTIME: str = "langgraph"
    AGENT_TASK_RUNTIME_DEFAULT_MODE: str = "none"
    AGENT_TASK_RUNTIME_ALLOW_DEEP: bool = False
    AGENT_TASK_RUNTIME_REQUIRE_DEEP_CONFIRMATION: bool = True
    AGENT_TASK_RUNTIME_DEEP_ALLOWED_ACTORS: str = "human,operator,admin"
    AGENT_TASK_LANGGRAPH_CHECKPOINT_NS: str = "agent-task"
