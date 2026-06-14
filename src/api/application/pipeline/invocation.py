"""Helpers for building runner invocation context from pipeline events."""
from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

from api.application.contracts import SafetyLevel, ToolInvocation
from api.infrastructure.schemas.models.process_event import ProcessEvent

_CONTEXT_KEYS = {
    "action_id",
    "capability_id",
    "profile_id",
    "safety_level",
    "policy_decision_id",
    "scope_decision_id",
    "campaign_id",
    "requested_by",
    "options",
}
_EVENT_KEYS = {
    "event",
    "event_id",
    "program_id",
    "targets",
    "target",
    "source",
    "confidence",
    "job_id",
    "run_id",
    "correlation_id",
    "causation_id",
    "profile",
    "payload",
    "created_at",
}
_TARGET_PARAM_NAMES = {
    "targets",
    "target",
    "hosts",
    "host",
    "urls",
    "url",
    "ips",
    "ip",
    "domains",
    "domain",
    "js_urls",
}


def option_map(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return action options from a legacy event dict."""
    direct = event.get("options")
    if isinstance(direct, Mapping):
        return dict(direct)

    payload = event.get("payload")
    if isinstance(payload, Mapping):
        nested = payload.get("options")
        if isinstance(nested, Mapping):
            return dict(nested)
        return {
            str(key): value
            for key, value in payload.items()
            if key not in _CONTEXT_KEYS and key not in _EVENT_KEYS
        }

    return {
        str(key): value
        for key, value in event.items()
        if key not in _CONTEXT_KEYS and key not in _EVENT_KEYS
    }


def build_invocation(
    event: Mapping[str, Any],
    targets: list[str],
) -> ToolInvocation | None:
    """Build ToolInvocation when an event carries complete action context."""
    try:
        return ToolInvocation(
            action_id=UUID(str(event["action_id"])),
            job_id=UUID(str(event["job_id"])),
            run_id=UUID(str(event["run_id"])),
            program_id=UUID(str(event["program_id"])),
            capability_id=str(event["capability_id"]),
            profile_id=str(event["profile_id"]),
            targets=targets,
            options=option_map(event),
            safety_level=SafetyLevel(str(event["safety_level"])),
            scope_decision_id=UUID(str(event["scope_decision_id"])),
            policy_decision_id=UUID(str(event["policy_decision_id"])),
            campaign_id=UUID(str(event["campaign_id"])),
            correlation_id=UUID(str(event["correlation_id"])),
            requested_by=(str(event["requested_by"]) if event.get("requested_by") else None),
            source_event_id=(UUID(str(event["event_id"])) if event.get("event_id") else None),
            payload=dict(event.get("payload") or {}),
        )
    except (KeyError, TypeError, ValueError):
        return None


def metadata(invocation: ToolInvocation | None) -> dict[str, Any]:
    """Return compact raw-artifact metadata from invocation context."""
    if invocation is None:
        return {}
    return {
        "action_id": str(invocation.action_id),
        "capability_id": invocation.capability_id,
        "profile_id": invocation.profile_id,
        "policy_decision_id": str(invocation.policy_decision_id),
        "scope_decision_id": str(invocation.scope_decision_id),
        "safety_level": invocation.safety_level.value,
    }


def run_raw(
    runner: Any,
    targets: list[str] | str,
    invocation: ToolInvocation | None = None,
) -> AsyncIterator[ProcessEvent]:
    """Call runner.run_raw with only supported action options."""
    options = invocation.options if invocation is not None else {}
    method = runner.run_raw
    signature = inspect.signature(method)
    params = signature.parameters
    accepts_any = any(
        param.kind is inspect.Parameter.VAR_KEYWORD
        for param in params.values()
    )
    if accepts_any:
        return method(targets, **options)

    accepted = {
        name
        for name, param in params.items()
        if name not in _TARGET_PARAM_NAMES
        and param.kind
        in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    }
    kwargs = {key: value for key, value in options.items() if key in accepted}
    return method(targets, **kwargs)
