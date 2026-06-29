"""Compact read-side summaries for agent runtime spend.

The agent workspace should show whether agent answers used no-model, cheap,
normal, or deep runtime modes without exposing provider costs or internal runtime
implementation. This module only summarizes already-durable task message
metadata; it does not run models, agents, graph algorithms, or tools.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from api.application.agent_tasks import AgentTaskMessageRecord


_RUNTIME_MODES = ("none", "cheap", "normal", "deep")


class AgentRuntimeUsageSummary(BaseModel):
    """Human-facing runtime spend summary for agent task messages."""

    model_config = ConfigDict(extra="forbid")

    total_messages: int = 0
    user_requested_messages: int = 0
    runtime_decision_messages: int = 0
    selected_modes: dict[str, int] = Field(default_factory=dict)
    requested_modes: dict[str, int] = Field(default_factory=dict)
    llm_allowed_messages: int = 0
    no_model_messages: int = 0
    downgraded_messages: int = 0
    deep_requested_messages: int = 0
    deep_approved_messages: int = 0
    deep_downgraded_messages: int = 0
    context_truncated_messages: int = 0
    latest_selected_mode: str | None = None
    latest_requested_mode: str | None = None
    latest_reason_code: str | None = None
    warnings: list[str] = Field(default_factory=list)




class AgentRuntimeUsageAggregateRecord(BaseModel):
    """Durable per-day runtime usage aggregate for a program/campaign."""

    model_config = ConfigDict(extra="forbid")

    program_id: Any
    campaign_id: Any | None = None
    usage_date: Any
    total_agent_messages: int = 0
    runtime_decision_messages: int = 0
    selected_modes: dict[str, int] = Field(default_factory=dict)
    requested_modes: dict[str, int] = Field(default_factory=dict)
    llm_allowed_messages: int = 0
    no_model_messages: int = 0
    downgraded_messages: int = 0
    deep_requested_messages: int = 0
    deep_approved_messages: int = 0
    deep_downgraded_messages: int = 0
    context_truncated_messages: int = 0
    latest_selected_mode: str | None = None
    latest_requested_mode: str | None = None
    latest_reason_code: str | None = None


class AgentRuntimeUsageDelta(BaseModel):
    """Single durable increment extracted from one visible agent reply."""

    model_config = ConfigDict(extra="forbid")

    requested_mode: str
    selected_mode: str
    reason_code: str | None = None
    llm_allowed: bool = False
    downgraded: bool = False
    deep_requested: bool = False
    deep_approved: bool = False
    deep_downgraded: bool = False
    context_truncated: bool = False


def runtime_usage_delta_from_metadata(metadata: dict[str, Any]) -> AgentRuntimeUsageDelta | None:
    """Extract one runtime usage delta from agent message metadata.

    Returns None when the message has no backend budget decision. This keeps
    user prompts, system notes, and old messages from polluting durable usage
    aggregates.
    """

    budget = _dict(metadata.get("budget"))
    if not budget:
        return None

    requested_mode = _mode(budget.get("requested_mode")) or "none"
    selected_mode = _mode(budget.get("selected_mode")) or requested_mode
    reason_code = _first_text(budget.get("reason_code"))
    deep_approval = _dict(budget.get("deep_approval"))
    observed = _dict(budget.get("observed"))
    truncated = (
        _int(observed.get("prompt_chars_after")) < _int(observed.get("prompt_chars_before"))
        or _int(observed.get("context_refs_after")) < _int(observed.get("context_refs_before"))
        or (reason_code or "").endswith("_with_truncation")
    )

    return AgentRuntimeUsageDelta(
        requested_mode=requested_mode,
        selected_mode=selected_mode,
        reason_code=reason_code,
        llm_allowed=bool(budget.get("llm_allowed")),
        downgraded=requested_mode != selected_mode,
        deep_requested=requested_mode == "deep",
        deep_approved=deep_approval.get("reason_code") == "deep_mode_approved"
        or (requested_mode == "deep" and selected_mode == "deep"),
        deep_downgraded=requested_mode == "deep" and selected_mode != "deep",
        context_truncated=truncated,
    )


def summarize_agent_runtime_usage_aggregates(
    rows: Iterable[AgentRuntimeUsageAggregateRecord | dict[str, Any]],
) -> AgentRuntimeUsageSummary:
    """Summarize durable daily aggregates into the existing UI summary shape."""

    selected_modes: Counter[str] = Counter()
    requested_modes: Counter[str] = Counter()
    total_messages = 0
    runtime_decision_messages = 0
    llm_allowed_messages = 0
    no_model_messages = 0
    downgraded_messages = 0
    deep_requested_messages = 0
    deep_approved_messages = 0
    deep_downgraded_messages = 0
    context_truncated_messages = 0
    latest_selected_mode: str | None = None
    latest_requested_mode: str | None = None
    latest_reason_code: str | None = None
    latest_date: Any = None

    for raw in rows:
        row = raw.model_dump() if isinstance(raw, AgentRuntimeUsageAggregateRecord) else dict(raw)
        total_messages += _int(row.get("total_agent_messages"))
        runtime_decision_messages += _int(row.get("runtime_decision_messages"))
        llm_allowed_messages += _int(row.get("llm_allowed_messages"))
        no_model_messages += _int(row.get("no_model_messages"))
        downgraded_messages += _int(row.get("downgraded_messages"))
        deep_requested_messages += _int(row.get("deep_requested_messages"))
        deep_approved_messages += _int(row.get("deep_approved_messages"))
        deep_downgraded_messages += _int(row.get("deep_downgraded_messages"))
        context_truncated_messages += _int(row.get("context_truncated_messages"))
        for mode, count in _dict(row.get("selected_modes")).items():
            normalized = _mode(mode)
            if normalized:
                selected_modes[normalized] += _int(count)
        for mode, count in _dict(row.get("requested_modes")).items():
            normalized = _mode(mode)
            if normalized:
                requested_modes[normalized] += _int(count)
        usage_date = row.get("usage_date")
        if latest_date is None or (usage_date is not None and usage_date >= latest_date):
            latest_date = usage_date
            latest_selected_mode = _mode(row.get("latest_selected_mode"))
            latest_requested_mode = _mode(row.get("latest_requested_mode"))
            latest_reason_code = _first_text(row.get("latest_reason_code"))

    return AgentRuntimeUsageSummary(
        total_messages=total_messages,
        user_requested_messages=runtime_decision_messages,
        runtime_decision_messages=runtime_decision_messages,
        selected_modes=_stable_mode_dict(selected_modes),
        requested_modes=_stable_mode_dict(requested_modes),
        llm_allowed_messages=llm_allowed_messages,
        no_model_messages=no_model_messages,
        downgraded_messages=downgraded_messages,
        deep_requested_messages=deep_requested_messages,
        deep_approved_messages=deep_approved_messages,
        deep_downgraded_messages=deep_downgraded_messages,
        context_truncated_messages=context_truncated_messages,
        latest_selected_mode=latest_selected_mode,
        latest_requested_mode=latest_requested_mode,
        latest_reason_code=latest_reason_code,
        warnings=_warnings(
            runtime_decision_messages=runtime_decision_messages,
            downgraded_messages=downgraded_messages,
            deep_downgraded_messages=deep_downgraded_messages,
            context_truncated_messages=context_truncated_messages,
        ),
    )

def summarize_agent_runtime_usage(messages: Iterable[AgentTaskMessageRecord]) -> AgentRuntimeUsageSummary:
    """Summarize runtime mode metadata from visible agent task messages.

    User messages carry requested mode metadata from the UI. Agent messages carry
    backend budget decisions after runtime execution. We keep both views because
    they answer different UI questions: what the human asked for and what the
    backend actually allowed.
    """

    ordered = list(messages)
    requested_modes: Counter[str] = Counter()
    selected_modes: Counter[str] = Counter()
    user_requested_messages = 0
    runtime_decision_messages = 0
    llm_allowed_messages = 0
    no_model_messages = 0
    downgraded_messages = 0
    deep_requested_messages = 0
    deep_approved_messages = 0
    deep_downgraded_messages = 0
    context_truncated_messages = 0
    latest_selected_mode: str | None = None
    latest_requested_mode: str | None = None
    latest_reason_code: str | None = None

    for message in ordered:
        metadata = _dict(message.metadata)
        requested_from_message = _mode(
            _first_text(
                metadata.get("agent_runtime_mode"),
                metadata.get("budget_mode"),
                metadata.get("model_mode"),
            )
        )
        if requested_from_message:
            user_requested_messages += 1
            requested_modes[requested_from_message] += 1

        budget = _dict(metadata.get("budget"))
        if not budget:
            continue

        runtime_decision_messages += 1
        requested_mode = _mode(budget.get("requested_mode")) or requested_from_message or "none"
        selected_mode = _mode(budget.get("selected_mode")) or requested_mode
        reason_code = _first_text(budget.get("reason_code"))
        deep_approval = _dict(budget.get("deep_approval"))

        requested_modes[requested_mode] += 0  # ensures stable keys after normalization below
        selected_modes[selected_mode] += 1
        latest_selected_mode = selected_mode
        latest_requested_mode = requested_mode
        latest_reason_code = reason_code

        llm_allowed = bool(budget.get("llm_allowed"))
        if llm_allowed:
            llm_allowed_messages += 1
        else:
            no_model_messages += 1

        if requested_mode != selected_mode:
            downgraded_messages += 1

        if requested_mode == "deep":
            deep_requested_messages += 1
            if selected_mode != "deep":
                deep_downgraded_messages += 1

        if deep_approval.get("reason_code") == "deep_mode_approved" or (requested_mode == "deep" and selected_mode == "deep"):
            deep_approved_messages += 1

        observed = _dict(budget.get("observed"))
        truncated = (
            _int(observed.get("prompt_chars_after")) < _int(observed.get("prompt_chars_before"))
            or _int(observed.get("context_refs_after")) < _int(observed.get("context_refs_before"))
            or (reason_code or "").endswith("_with_truncation")
        )
        if truncated:
            context_truncated_messages += 1

    return AgentRuntimeUsageSummary(
        total_messages=len(ordered),
        user_requested_messages=user_requested_messages,
        runtime_decision_messages=runtime_decision_messages,
        selected_modes=_stable_mode_dict(selected_modes),
        requested_modes=_stable_mode_dict(requested_modes),
        llm_allowed_messages=llm_allowed_messages,
        no_model_messages=no_model_messages,
        downgraded_messages=downgraded_messages,
        deep_requested_messages=deep_requested_messages,
        deep_approved_messages=deep_approved_messages,
        deep_downgraded_messages=deep_downgraded_messages,
        context_truncated_messages=context_truncated_messages,
        latest_selected_mode=latest_selected_mode,
        latest_requested_mode=latest_requested_mode,
        latest_reason_code=latest_reason_code,
        warnings=_warnings(
            runtime_decision_messages=runtime_decision_messages,
            downgraded_messages=downgraded_messages,
            deep_downgraded_messages=deep_downgraded_messages,
            context_truncated_messages=context_truncated_messages,
        ),
    )



def _warnings(
    *,
    runtime_decision_messages: int,
    downgraded_messages: int,
    deep_downgraded_messages: int,
    context_truncated_messages: int,
) -> list[str]:
    warnings: list[str] = []
    if runtime_decision_messages == 0:
        warnings.append("no_runtime_decisions_yet")
    if downgraded_messages:
        warnings.append("runtime_mode_downgraded")
    if deep_downgraded_messages:
        warnings.append("deep_mode_downgraded")
    if context_truncated_messages:
        warnings.append("context_truncated")
    return warnings



def _stable_mode_dict(counter: Counter[str]) -> dict[str, int]:
    return {mode: int(counter.get(mode, 0)) for mode in _RUNTIME_MODES}



def _mode(value: Any) -> str | None:
    text = _first_text(value)
    if not text:
        return None
    normalized = text.strip().lower().replace("_", "-")
    aliases = {
        "off": "none",
        "disabled": "none",
        "deterministic": "none",
        "none": "none",
        "small": "cheap",
        "economy": "cheap",
        "cheap": "cheap",
        "standard": "normal",
        "normal": "normal",
        "expensive": "deep",
        "deep": "deep",
    }
    return aliases.get(normalized)



def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}



def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None



def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
