"""Helpers for building runner invocation context from pipeline events."""
from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

from api.application.action_invocation_payload import action_invocation_mapping
from api.application.contracts import (
    RunnerInvocationContext,
    SafetyLevel,
    ToolInvocation,
)
from api.application.execution_limits import ExecutionBudget
from api.application.process_event_contracts import ProcessEvent

LINEAGE_PAYLOAD_KEY = "execution_lineage"
RUNNER_CONTEXT_PAYLOAD_KEY = "runner_invocation_context"

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


InvocationContext = ToolInvocation | RunnerInvocationContext


def option_map(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return action options from current nested or legacy event dicts."""
    direct = event.get("options")
    if isinstance(direct, Mapping):
        return dict(direct)

    payload = _payload_mapping(event)
    legacy_payload_options = payload.get("options")
    if isinstance(legacy_payload_options, Mapping):
        return dict(legacy_payload_options)

    action_payload_options = action_invocation_mapping(payload).get("options")
    if isinstance(action_payload_options, Mapping):
        return dict(action_payload_options)
    return {}


def build_invocation(
    event: Mapping[str, Any],
    targets: list[str],
) -> ToolInvocation | None:
    """Build ToolInvocation when an event carries complete action context."""
    try:
        payload = dict(event.get("payload") or {})
        action_payload = action_invocation_mapping(payload)
        parent_artifact_id = (
            event.get("parent_artifact_id")
            or payload.get("parent_artifact_id")
            or action_payload.get("parent_artifact_id")
        )
        return ToolInvocation(
            action_id=UUID(str(_event_value(event, payload, action_payload, "action_id"))),
            job_id=UUID(str(event["job_id"])),
            run_id=UUID(str(event["run_id"])),
            program_id=UUID(str(event["program_id"])),
            capability_id=str(_event_value(event, payload, action_payload, "capability_id")),
            profile_id=str(_event_value(event, payload, action_payload, "profile_id")),
            targets=targets,
            options=option_map(event),
            execution_budget=ExecutionBudget.model_validate(
                _event_value(event, payload, action_payload, "execution_budget")
            ),
            safety_level=SafetyLevel(
                str(_event_value(event, payload, action_payload, "safety_level"))
            ),
            scope_decision_id=UUID(
                str(_event_value(event, payload, action_payload, "scope_decision_id"))
            ),
            policy_decision_id=UUID(
                str(_event_value(event, payload, action_payload, "policy_decision_id"))
            ),
            campaign_id=UUID(
                str(_event_value(event, payload, action_payload, "campaign_id"))
            ),
            correlation_id=UUID(str(event["correlation_id"])),
            requested_by=(
                str(_event_optional_value(event, payload, action_payload, "requested_by"))
                if _event_optional_value(event, payload, action_payload, "requested_by")
                else None
            ),
            source_event_id=(UUID(str(event["event_id"])) if event.get("event_id") else None),
            parent_artifact_id=(
                UUID(str(parent_artifact_id))
                if parent_artifact_id
                else None
            ),
            payload=payload,
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_runner_context(
    event: Mapping[str, Any],
    targets: list[str],
    *,
    node_id: str,
) -> RunnerInvocationContext | None:
    """Build current-node execution context without faking tool identity.

    Downstream events usually do not carry the original action capability/profile
    as top-level fields. This context preserves root lineage and inherited hard
    ceilings while keeping the current runner identity at the node level.
    """
    try:
        payload = _payload_mapping(event)
        action_payload = action_invocation_mapping(payload)
        lineage = _lineage_mapping(event)
        context = _runner_context_values(event, payload, action_payload, lineage)
        return RunnerInvocationContext(
            job_id=_optional_uuid(event.get("job_id")),
            run_id=_optional_uuid(event.get("run_id")),
            program_id=UUID(str(event["program_id"])),
            node_id=node_id,
            targets=targets,
            options={},
            execution_budget=(
                ExecutionBudget.model_validate(context["budget"])
                if context["budget"]
                else None
            ),
            safety_level=(
                SafetyLevel(str(context["safety_level"]))
                if context["safety_level"]
                else None
            ),
            scope_decision_id=_optional_uuid(context["scope_decision_id"]),
            policy_decision_id=_optional_uuid(context["policy_decision_id"]),
            campaign_id=_optional_uuid(context["campaign_id"]),
            correlation_id=_optional_uuid(context["correlation_id"]),
            requested_by=_optional_text(context["requested_by"]),
            source_event_id=_optional_uuid(event.get("event_id")),
            parent_artifact_id=_optional_uuid(context["parent_artifact_id"]),
            root_action_id=_optional_uuid(context["root_action_id"]),
            root_capability_id=_optional_text(context["root_capability_id"]),
            root_profile_id=_optional_text(context["root_profile_id"]),
            upstream_node_id=_optional_text(context["upstream_node_id"]),
            payload=payload,
        )
    except (KeyError, TypeError, ValueError):
        return None


def metadata(
    invocation: ToolInvocation | None,
    runner_context: RunnerInvocationContext | None = None,
) -> dict[str, Any]:
    """Return compact raw-artifact metadata from execution context."""
    data: dict[str, Any] = {}
    if invocation is not None:
        data.update(
            {
                "action_id": str(invocation.action_id),
                "capability_id": invocation.capability_id,
                "profile_id": invocation.profile_id,
                "policy_decision_id": str(invocation.policy_decision_id),
                "scope_decision_id": str(invocation.scope_decision_id),
                "parent_artifact_id": (
                    str(invocation.parent_artifact_id)
                    if invocation.parent_artifact_id
                    else None
                ),
                "safety_level": invocation.safety_level.value,
            }
        )
    if runner_context is not None:
        data.update(
            {
                "runner_context_version": "runner-context-v1",
                "node_id": runner_context.node_id,
                "root_action_id": (
                    str(runner_context.root_action_id)
                    if runner_context.root_action_id
                    else None
                ),
                "root_capability_id": runner_context.root_capability_id,
                "root_profile_id": runner_context.root_profile_id,
                "upstream_node_id": runner_context.upstream_node_id,
            }
        )
        if not data.get("safety_level") and runner_context.safety_level is not None:
            data["safety_level"] = runner_context.safety_level.value
        if not data.get("policy_decision_id") and runner_context.policy_decision_id:
            data["policy_decision_id"] = str(runner_context.policy_decision_id)
        if not data.get("scope_decision_id") and runner_context.scope_decision_id:
            data["scope_decision_id"] = str(runner_context.scope_decision_id)
        if not data.get("parent_artifact_id") and runner_context.parent_artifact_id:
            data["parent_artifact_id"] = str(runner_context.parent_artifact_id)
    return {key: value for key, value in data.items() if value is not None}


def run_raw(
    runner: Any,
    targets: list[str] | str,
    invocation: InvocationContext | None = None,
) -> AsyncIterator[ProcessEvent]:
    """Call runner.run_raw with only supported action options."""
    method = runner.run_raw
    signature = inspect.signature(method)
    params = signature.parameters
    options = dict(invocation.options if invocation is not None else {})
    accepts_any = any(
        param.kind is inspect.Parameter.VAR_KEYWORD
        for param in params.values()
    )
    accepted_option_names = getattr(runner, "accepted_option_names", None)

    def supports_option(name: str) -> bool:
        if name in params:
            return True
        if not accepts_any:
            return False
        return accepted_option_names is None or name in accepted_option_names

    budget = invocation.execution_budget if invocation is not None else None
    if budget is not None:
        if budget.max_duration_seconds is not None and supports_option("timeout"):
            requested_timeout = options.get(
                "timeout",
                budget.max_duration_seconds,
            )
            options["timeout"] = min(
                float(requested_timeout),
                budget.max_duration_seconds,
            )
        if budget.rate_per_second is not None and supports_option("rate"):
            requested_rate = options.get("rate", budget.rate_per_second)
            options["rate"] = min(
                float(requested_rate),
                budget.rate_per_second,
            )
        if budget.concurrency is not None and supports_option("concurrency"):
            options["concurrency"] = budget.concurrency

    if accepts_any:
        if accepted_option_names is None:
            return method(targets, **options)
        return method(
            targets,
            **{key: value for key, value in options.items() if key in accepted_option_names},
        )

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


def _runner_context_values(
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    action_payload: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    upstream_runner = _upstream_runner_context(event)
    return {
        "budget": _first_value(
            event.get("execution_budget"),
            payload.get("execution_budget"),
            action_payload.get("execution_budget"),
            lineage.get("root_execution_budget"),
        ),
        "safety_level": _first_value(
            event.get("safety_level"),
            payload.get("safety_level"),
            action_payload.get("safety_level"),
            lineage.get("root_safety_level"),
        ),
        "scope_decision_id": _first_value(
            event.get("scope_decision_id"),
            payload.get("scope_decision_id"),
            action_payload.get("scope_decision_id"),
            lineage.get("scope_decision_id"),
        ),
        "policy_decision_id": _first_value(
            event.get("policy_decision_id"),
            payload.get("policy_decision_id"),
            action_payload.get("policy_decision_id"),
            lineage.get("policy_decision_id"),
        ),
        "campaign_id": _first_value(
            event.get("campaign_id"),
            action_payload.get("campaign_id"),
            lineage.get("campaign_id"),
        ),
        "correlation_id": _first_value(
            event.get("correlation_id"),
            lineage.get("correlation_id"),
        ),
        "requested_by": _first_value(
            event.get("requested_by"),
            payload.get("requested_by"),
            action_payload.get("requested_by"),
            lineage.get("requested_by"),
        ),
        "parent_artifact_id": _first_value(
            event.get("parent_artifact_id"),
            payload.get("parent_artifact_id"),
            action_payload.get("parent_artifact_id"),
        ),
        "root_action_id": _first_value(
            event.get("action_id"),
            payload.get("action_id"),
            action_payload.get("action_id"),
            lineage.get("root_action_id"),
        ),
        "root_capability_id": _first_value(
            event.get("capability_id"),
            payload.get("capability_id"),
            action_payload.get("capability_id"),
            lineage.get("root_capability_id"),
        ),
        "root_profile_id": _first_value(
            event.get("profile_id"),
            payload.get("profile_id"),
            action_payload.get("profile_id"),
            lineage.get("root_profile_id"),
        ),
        "upstream_node_id": upstream_runner.get("node_id"),
    }


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _optional_text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _event_value(
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    action_payload: Mapping[str, Any],
    key: str,
) -> Any:
    if key in event:
        return event[key]
    if key in payload:
        return payload[key]
    return action_payload[key]


def _event_optional_value(
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    action_payload: Mapping[str, Any],
    key: str,
) -> Any:
    if key in event:
        return event[key]
    if key in payload:
        return payload[key]
    return action_payload.get(key)


def _payload_mapping(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _lineage_mapping(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _payload_mapping(event)
    lineage = event.get(LINEAGE_PAYLOAD_KEY) or payload.get(LINEAGE_PAYLOAD_KEY)
    return lineage if isinstance(lineage, Mapping) else {}


def _upstream_runner_context(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = _payload_mapping(event)
    context = event.get(RUNNER_CONTEXT_PAYLOAD_KEY) or payload.get(
        RUNNER_CONTEXT_PAYLOAD_KEY
    )
    return context if isinstance(context, Mapping) else {}


def _optional_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
