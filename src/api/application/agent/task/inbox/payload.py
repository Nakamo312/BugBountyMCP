"""Parsing helpers for agent-task inbox handoff payloads."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.agent.task.inbox.models import AgentTaskInboxBridgeResult
from api.application.agent_task_runtime_contracts import AgentTaskRuntimeRequest
from api.application.agent_tasks import (
    AGENT_TASK_FOLLOWUP_SCHEMA_VERSION,
    AGENT_TASK_PROMPT_SCHEMA_VERSION,
)


SUPPORTED_AGENT_TASK_SCHEMA_VERSIONS = frozenset(
    {
        AGENT_TASK_PROMPT_SCHEMA_VERSION,
        AGENT_TASK_FOLLOWUP_SCHEMA_VERSION,
    }
)


def runtime_request_from_agent_task_message(message: dict[str, Any]) -> AgentTaskRuntimeRequest:
    payload = dict(message.get("payload") or {})
    schema_version = str(payload.get("schema_version") or "")
    if schema_version not in SUPPORTED_AGENT_TASK_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported agent task schema_version: {schema_version}")

    body_excerpt = _first_text(payload.get("prompt_excerpt"), payload.get("body_excerpt"))
    if body_excerpt is None:
        raise ValueError("agent task payload must contain prompt_excerpt or body_excerpt")

    metadata = dict(payload.get("metadata") or {})
    _copy_text(metadata, "created_by", payload.get("created_by"))
    _copy_text(metadata, "source", payload.get("source"))

    return AgentTaskRuntimeRequest(
        task_id=_required_uuid(payload, "task_id"),
        message_id=_required_uuid(payload, "message_id"),
        program_id=_required_uuid(message, "program_id"),
        campaign_id=_optional_uuid(message.get("campaign_id") or payload.get("campaign_id")),
        correlation_id=_optional_uuid(message.get("correlation_id") or payload.get("correlation_id")),
        target_agent=_first_text(payload.get("target_agent")) or "coordinator",
        schema_version=schema_version,
        body_excerpt=body_excerpt,
        body_hash=_first_text(payload.get("prompt_hash"), payload.get("body_hash")),
        context_refs=tuple(
            dict(item) for item in payload.get("context_refs") or [] if isinstance(item, dict)
        ),
        metadata=metadata,
        source=_first_text(payload.get("source")),
    )


def unsupported_message_result(message: dict[str, Any]) -> AgentTaskInboxBridgeResult:
    return AgentTaskInboxBridgeResult(
        message_id=_required_uuid(message, "id"),
        task_id=None,
        outcome="skipped",
        acknowledged=True,
        reason_code="unsupported_message_type",
    )


def _copy_text(target: dict[str, Any], key: str, value: Any) -> None:
    text = _first_text(value)
    if text:
        target.setdefault(key, text)


def _required_uuid(message: dict[str, Any], field: str) -> UUID:
    value = message.get(field)
    if value is None:
        raise ValueError(f"{field} is required for agent task inbox bridge")
    return _parse_uuid(value)


def _optional_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    return _parse_uuid(value)


def _parse_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def error_summary(exc: Exception, *, max_length: int = 4000) -> str:
    message = f"{type(exc).__name__}: {exc}".strip()
    return (message or type(exc).__name__)[:max_length]
