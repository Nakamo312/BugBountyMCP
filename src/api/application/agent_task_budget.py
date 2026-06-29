"""Budget guard for agent task runtimes.

Agent tasks are allowed to feel like a promptable workspace, but a prompt must not
turn into an unbounded LLM bill. This module sits in front of the concrete
runtime and converts human/agent intent into a bounded execution mode. It trims
context before a runtime sees it, blocks deep mode unless explicitly enabled, and
records the budget decision in the visible agent reply metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from api.application.agent_task_runtime_contracts import (
    AgentTaskRuntime,
    AgentTaskRuntimeRequest,
    AgentTaskRuntimeResult,
)


class AgentTaskBudgetMode(str, Enum):
    """Runtime spend tier for an agent task."""

    NONE = "none"
    CHEAP = "cheap"
    NORMAL = "normal"
    DEEP = "deep"


@dataclass(frozen=True, slots=True)
class AgentTaskBudgetLimits:
    """Hard per-invocation limits applied before a runtime sees context."""

    max_prompt_chars: int
    max_context_refs: int
    max_output_chars: int
    llm_allowed: bool
    deep_mode: bool = False


@dataclass(frozen=True, slots=True)
class AgentTaskDeepApprovalDecision:
    """Server-side gate for deep agent runtime mode."""

    requested: bool
    globally_allowed: bool
    confirmation_required: bool
    confirmation_provided: bool
    actor: str | None
    actor_allowed: bool
    allowed_actors: tuple[str, ...]
    approved: bool
    reason_code: str

    def as_metadata(self) -> dict[str, Any]:
        return {
            "policy": "agent-task-deep-runtime-approval.v1",
            "requested": self.requested,
            "globally_allowed": self.globally_allowed,
            "confirmation_required": self.confirmation_required,
            "confirmation_provided": self.confirmation_provided,
            "actor": self.actor,
            "actor_allowed": self.actor_allowed,
            "allowed_actors": list(self.allowed_actors),
            "approved": self.approved,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class AgentTaskBudgetDecision:
    """Decision made for one agent task runtime invocation."""

    requested_mode: AgentTaskBudgetMode
    selected_mode: AgentTaskBudgetMode
    limits: AgentTaskBudgetLimits
    runtime_allowed: bool
    reason_code: str
    prompt_chars_before: int
    prompt_chars_after: int
    context_refs_before: int
    context_refs_after: int
    deep_approval: AgentTaskDeepApprovalDecision | None = None

    def bounded_request(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeRequest:
        return replace(
            request,
            body_excerpt=request.body_excerpt[: self.limits.max_prompt_chars],
            context_refs=tuple(request.context_refs[: self.limits.max_context_refs]),
        )

    def as_metadata(self) -> dict[str, Any]:
        metadata = {
            "policy": "agent-task-runtime-budget.v1",
            "requested_mode": self.requested_mode.value,
            "selected_mode": self.selected_mode.value,
            "runtime_allowed": self.runtime_allowed,
            "reason_code": self.reason_code,
            "llm_allowed": self.limits.llm_allowed,
            "deep_mode": self.limits.deep_mode,
            "limits": {
                "max_prompt_chars": self.limits.max_prompt_chars,
                "max_context_refs": self.limits.max_context_refs,
                "max_output_chars": self.limits.max_output_chars,
            },
            "observed": {
                "prompt_chars_before": self.prompt_chars_before,
                "prompt_chars_after": self.prompt_chars_after,
                "context_refs_before": self.context_refs_before,
                "context_refs_after": self.context_refs_after,
            },
        }
        if self.deep_approval is not None:
            metadata["deep_approval"] = self.deep_approval.as_metadata()
        return metadata


class AgentTaskRuntimeBudgetPolicy:
    """Select and enforce a spend tier for one agent task runtime call."""

    def __init__(
        self,
        *,
        default_mode: str | AgentTaskBudgetMode = AgentTaskBudgetMode.NONE,
        allow_deep: bool = False,
        require_deep_confirmation: bool = True,
        deep_allowed_actors: tuple[str, ...] | list[str] | str = ("human", "operator", "admin"),
    ) -> None:
        self.default_mode = _mode(default_mode, fallback=AgentTaskBudgetMode.NONE)
        self.allow_deep = bool(allow_deep)
        self.require_deep_confirmation = bool(require_deep_confirmation)
        self.deep_allowed_actors = _actor_set(deep_allowed_actors)

    def evaluate(self, request: AgentTaskRuntimeRequest) -> AgentTaskBudgetDecision:
        requested_mode = self._requested_mode(request)
        selected_mode = requested_mode
        reason_code = "selected"
        deep_approval: AgentTaskDeepApprovalDecision | None = None
        if requested_mode is AgentTaskBudgetMode.DEEP:
            deep_approval = self._deep_approval(request)
            reason_code = deep_approval.reason_code
            if not deep_approval.approved:
                selected_mode = AgentTaskBudgetMode.NORMAL
        limits = _limits_for(selected_mode)
        prompt_chars_before = len(request.body_excerpt)
        context_refs_before = len(request.context_refs)
        prompt_chars_after = min(prompt_chars_before, limits.max_prompt_chars)
        context_refs_after = min(context_refs_before, limits.max_context_refs)
        if selected_mode is AgentTaskBudgetMode.NONE:
            reason_code = "model_usage_disabled"
        elif prompt_chars_after < prompt_chars_before or context_refs_after < context_refs_before:
            reason_code = f"{reason_code}_with_truncation"
        return AgentTaskBudgetDecision(
            requested_mode=requested_mode,
            selected_mode=selected_mode,
            limits=limits,
            runtime_allowed=selected_mode is not AgentTaskBudgetMode.NONE,
            reason_code=reason_code,
            prompt_chars_before=prompt_chars_before,
            prompt_chars_after=prompt_chars_after,
            context_refs_before=context_refs_before,
            context_refs_after=context_refs_after,
            deep_approval=deep_approval,
        )

    def _deep_approval(self, request: AgentTaskRuntimeRequest) -> AgentTaskDeepApprovalDecision:
        metadata = request.metadata or {}
        actor = _first_text(
            metadata.get("deep_mode_actor"),
            metadata.get("created_by"),
            metadata.get("actor"),
            metadata.get("requested_by"),
            request.source,
        )
        normalized_actor = _actor(actor) if actor else None
        confirmation_provided = _truthy(
            metadata.get("deep_mode_confirmed"),
            metadata.get("deep_mode_approved"),
            metadata.get("deep_confirmed"),
            metadata.get("deep_approved"),
        )
        actor_allowed = bool(
            normalized_actor
            and ("*" in self.deep_allowed_actors or normalized_actor in self.deep_allowed_actors)
        )
        if not self.allow_deep:
            reason_code = "deep_mode_disabled"
        elif self.require_deep_confirmation and not confirmation_provided:
            reason_code = "deep_mode_requires_explicit_confirmation"
        elif not actor_allowed:
            reason_code = "deep_mode_actor_not_allowed"
        else:
            reason_code = "deep_mode_approved"
        approved = reason_code == "deep_mode_approved"
        return AgentTaskDeepApprovalDecision(
            requested=True,
            globally_allowed=self.allow_deep,
            confirmation_required=self.require_deep_confirmation,
            confirmation_provided=confirmation_provided,
            actor=normalized_actor,
            actor_allowed=actor_allowed,
            allowed_actors=tuple(sorted(self.deep_allowed_actors)),
            approved=approved,
            reason_code=reason_code,
        )

    def _requested_mode(self, request: AgentTaskRuntimeRequest) -> AgentTaskBudgetMode:
        metadata = request.metadata or {}
        explicit = _first_text(
            metadata.get("agent_runtime_mode"),
            metadata.get("runtime_mode"),
            metadata.get("budget_mode"),
            metadata.get("model_mode"),
        )
        if explicit:
            return _mode(explicit, fallback=self.default_mode)
        return self.default_mode


class BudgetedAgentTaskRuntime:
    """Runtime wrapper that enforces an AgentTaskRuntimeBudgetPolicy.

    ``inner`` may be a LangGraph/LLM-backed runtime. ``fallback`` must be a cheap,
    deterministic runtime. If the selected mode is ``none``, this wrapper calls the
    fallback instead of the inner runtime.
    """

    def __init__(
        self,
        *,
        inner: AgentTaskRuntime,
        fallback: AgentTaskRuntime,
        policy: AgentTaskRuntimeBudgetPolicy,
    ) -> None:
        self.inner = inner
        self.fallback = fallback
        self.policy = policy

    async def handle(self, request: AgentTaskRuntimeRequest) -> AgentTaskRuntimeResult:
        decision = self.policy.evaluate(request)
        bounded_request = decision.bounded_request(request)
        runtime = self.inner if decision.runtime_allowed else self.fallback
        result = await runtime.handle(bounded_request)
        body = result.body[: decision.limits.max_output_chars]
        metadata = dict(result.metadata or {})
        metadata["budget"] = decision.as_metadata()
        metadata.setdefault(
            "boundary",
            {
                "tool_execution": "forbidden_from_agent_task_runtime",
                "next_step": "agent_may_reply_or_propose_bounded_action_request",
            },
        )
        return AgentTaskRuntimeResult(
            agent_key=result.agent_key,
            body=body,
            message_kind=result.message_kind,
            status=result.status,
            artifact_refs=result.artifact_refs,
            fact_refs=result.fact_refs,
            graph_refs=result.graph_refs,
            action_refs=result.action_refs,
            proposal_refs=result.proposal_refs,
            decision_refs=result.decision_refs,
            proposal_drafts=result.proposal_drafts,
            metadata=metadata,
        )


def _limits_for(mode: AgentTaskBudgetMode) -> AgentTaskBudgetLimits:
    if mode is AgentTaskBudgetMode.NONE:
        return AgentTaskBudgetLimits(
            max_prompt_chars=1_500,
            max_context_refs=8,
            max_output_chars=1_200,
            llm_allowed=False,
        )
    if mode is AgentTaskBudgetMode.CHEAP:
        return AgentTaskBudgetLimits(
            max_prompt_chars=2_000,
            max_context_refs=12,
            max_output_chars=1_500,
            llm_allowed=True,
        )
    if mode is AgentTaskBudgetMode.NORMAL:
        return AgentTaskBudgetLimits(
            max_prompt_chars=4_000,
            max_context_refs=25,
            max_output_chars=2_500,
            llm_allowed=True,
        )
    return AgentTaskBudgetLimits(
        max_prompt_chars=8_000,
        max_context_refs=60,
        max_output_chars=4_000,
        llm_allowed=True,
        deep_mode=True,
    )


def _actor_set(value: tuple[str, ...] | list[str] | str) -> set[str]:
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    actors = {_actor(item) for item in raw if str(item).strip()}
    return actors or {"human", "operator", "admin"}


def _actor(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _truthy(*values: Any) -> bool:
    for value in values:
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, str):
            if value.strip().lower() in {"1", "true", "yes", "y", "on", "approved", "confirmed"}:
                return True
            continue
        if isinstance(value, (int, float)) and value == 1:
            return True
    return False


def _mode(value: str | AgentTaskBudgetMode, *, fallback: AgentTaskBudgetMode) -> AgentTaskBudgetMode:
    if isinstance(value, AgentTaskBudgetMode):
        return value
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "off": AgentTaskBudgetMode.NONE,
        "disabled": AgentTaskBudgetMode.NONE,
        "deterministic": AgentTaskBudgetMode.NONE,
        "none": AgentTaskBudgetMode.NONE,
        "small": AgentTaskBudgetMode.CHEAP,
        "cheap": AgentTaskBudgetMode.CHEAP,
        "economy": AgentTaskBudgetMode.CHEAP,
        "normal": AgentTaskBudgetMode.NORMAL,
        "standard": AgentTaskBudgetMode.NORMAL,
        "deep": AgentTaskBudgetMode.DEEP,
        "expensive": AgentTaskBudgetMode.DEEP,
    }
    return aliases.get(normalized, fallback)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
