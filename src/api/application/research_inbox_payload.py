"""Payload parsing helpers for research inbox messages."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.hypotheses import HypothesisBuildRequest


def research_thread_id_for_inbox_message(message: dict[str, Any]) -> str:
    """Return the deterministic research graph thread id for an inbox message."""

    workflow_run_id = message.get("workflow_run_id")
    if workflow_run_id is not None:
        return str(workflow_run_id)
    message_id = _required_uuid(message, "id")
    return f"agent-inbox:{message_id}"


def hypothesis_request_from_inbox_message(
    message: dict[str, Any],
    *,
    default_limit: int = 25,
) -> HypothesisBuildRequest:
    """Build a pointer-only hypothesis request from an inbox message.

    The payload may be an EventEnvelope dump, a small agent protocol message, or
    a direct request object. Only stable IDs and result-set keys are copied.
    """

    payload = dict(message.get("payload") or {})
    nested_payload = dict(payload.get("payload") or {})
    request_payload = dict(
        payload.get("hypothesis_build_request")
        or payload.get("request")
        or nested_payload.get("hypothesis_build_request")
        or nested_payload.get("request")
        or {}
    )

    return HypothesisBuildRequest(
        program_id=_required_uuid(message, "program_id"),
        result_key=_first_text(
            request_payload.get("result_key"),
            payload.get("result_key"),
            nested_payload.get("result_key"),
        ),
        action_id=_optional_uuid(
            request_payload.get("action_id")
            or payload.get("action_id")
            or nested_payload.get("action_id")
        ),
        campaign_id=_optional_uuid(
            message.get("campaign_id")
            or request_payload.get("campaign_id")
            or payload.get("campaign_id")
            or nested_payload.get("campaign_id")
        ),
        workflow_id=_optional_uuid(
            message.get("workflow_id")
            or request_payload.get("workflow_id")
            or payload.get("workflow_id")
            or nested_payload.get("workflow_id")
        ),
        workflow_run_id=_optional_uuid(
            message.get("workflow_run_id")
            or request_payload.get("workflow_run_id")
            or payload.get("workflow_run_id")
            or nested_payload.get("workflow_run_id")
        ),
        limit=_bounded_limit(
            request_payload.get("limit")
            or payload.get("limit")
            or nested_payload.get("limit"),
            default_limit=default_limit,
        ),
    )


def _required_uuid(message: dict[str, Any], field: str) -> UUID:
    value = message.get(field)
    if value is None:
        raise ValueError(f"{field} is required for research inbox bridge")
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
            return value
    return None


def _bounded_limit(value: Any, *, default_limit: int) -> int:
    if value is None or value == "":
        return default_limit
    return max(1, min(int(value), 100))


def error_summary(exc: Exception, *, max_length: int = 4000) -> str:
    message = f"{type(exc).__name__}: {exc}".strip()
    if not message:
        message = type(exc).__name__
    return message[:max_length]
