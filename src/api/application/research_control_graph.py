"""Checkpointed research control graph for pointer-only hypothesis work."""
from __future__ import annotations

from typing import Any, Protocol, TypedDict
from uuid import UUID

from langgraph.types import Command, interrupt
from langgraph.graph import END, START, StateGraph

from api.application.hypotheses import HypothesisBuildRequest
from api.application.research_readiness import (
    ResearchReadinessDecision,
    ResearchReadinessGate,
)
from api.application.research_pass import ResearchPassResult
from api.application.projections import ProjectionKey


class ResearchWorkflow(Protocol):
    async def run(self, request: HypothesisBuildRequest) -> ResearchPassResult: ...


class HypothesisStepSelector(Protocol):
    async def select_hypotheses(
        self,
        *,
        program_id: UUID,
        status: str | tuple[str, ...] | None = ...,
        hypothesis_type: str | None = ...,
        min_priority_score: int = ...,
        limit: int = ...,
    ) -> dict[str, Any]: ...


class ResearchControlState(TypedDict, total=False):
    program_id: str
    result_key: str | None
    action_id: str | None
    campaign_id: str | None
    workflow_id: str | None
    workflow_run_id: str | None
    limit: int
    required_projections: list[dict[str, str]]
    readiness_status: str
    wait_condition_id: str | None
    wait_reason: str | None
    wait_reason_code: str | None
    wait_condition_type: str | None
    result_set_keys: list[str]
    hypothesis_ids: list[str]
    critic_statuses: list[str]
    draft_statuses: list[str]
    finding_ids: list[str]
    research_pass_status: str
    research_pass_summary: dict[str, int | str]
    selection_status: str
    selected_hypothesis_steps: list[dict[str, Any]]


class ResearchControlGraph:
    def __init__(
        self,
        *,
        research_workflow: ResearchWorkflow,
        checkpointer: Any,
        readiness_gate: ResearchReadinessGate | None = None,
        hypothesis_selector: HypothesisStepSelector | None = None,
    ) -> None:
        self.research_workflow = research_workflow
        self.readiness_gate = readiness_gate
        self.hypothesis_selector = hypothesis_selector
        builder = StateGraph(ResearchControlState)
        builder.add_node("research", self._run_research)
        if hypothesis_selector is not None:
            builder.add_node("select_next_steps", self._select_next_steps)
        if readiness_gate is None:
            builder.add_edge(START, "research")
        else:
            builder.add_node("check_readiness", self._check_readiness)
            builder.add_node("wait_for_readiness", self._wait_for_readiness)
            builder.add_edge(START, "check_readiness")
            builder.add_conditional_edges(
                "check_readiness",
                self._route_readiness,
                {
                    "ready": "research",
                    "waiting": "wait_for_readiness",
                },
            )
            builder.add_edge("wait_for_readiness", "check_readiness")
        if hypothesis_selector is None:
            builder.add_edge("research", END)
        else:
            builder.add_edge("research", "select_next_steps")
            builder.add_edge("select_next_steps", END)
        self.compiled = builder.compile(checkpointer=checkpointer)

    async def ainvoke(
        self,
        request: HypothesisBuildRequest,
        *,
        thread_id: str,
        required_projections: tuple[ProjectionKey, ...] = (),
    ) -> ResearchControlState:
        return await self.compiled.ainvoke(
            self._input_state(request, required_projections),
            config=self._config(thread_id),
        )

    async def aget_state(self, *, thread_id: str):
        return await self.compiled.aget_state(self._config(thread_id))

    async def aresume(self, *, thread_id: str) -> ResearchControlState:
        result = await self.compiled.ainvoke(
            Command(resume=True),
            config=self._config(thread_id),
        )
        if result is not None:
            return result
        return (await self.aget_state(thread_id=thread_id)).values

    async def _check_readiness(
        self,
        state: ResearchControlState,
    ) -> ResearchControlState:
        if self.readiness_gate is None:
            return {"readiness_status": "ready"}
        decision = await self.readiness_gate.evaluate(
            self._request(state),
            required_projections=self._projection_keys(state),
        )
        return self._readiness_state(decision)

    @staticmethod
    def _route_readiness(state: ResearchControlState) -> str:
        return "ready" if state.get("readiness_status") == "ready" else "waiting"

    @staticmethod
    def _wait_for_readiness(
        state: ResearchControlState,
    ) -> ResearchControlState:
        interrupt(
            {
                "wait_condition_id": state.get("wait_condition_id"),
                "reason": state.get("wait_reason"),
                "reason_code": state.get("wait_reason_code"),
                "condition_type": state.get("wait_condition_type"),
            }
        )
        return {"readiness_status": "checking"}

    async def _run_research(
        self,
        state: ResearchControlState,
    ) -> ResearchControlState:
        result = await self.research_workflow.run(self._request(state))
        summary = result.safe_summary()
        return {
            "hypothesis_ids": [
                str(item.hypothesis.hypothesis_id) for item in result.items
            ],
            "critic_statuses": [item.critic.status for item in result.items],
            "draft_statuses": [item.report_draft.status for item in result.items],
            "finding_ids": [str(value) for value in result.finding_ids],
            "research_pass_status": str(summary["status"]),
            "research_pass_summary": summary,
        }

    async def _select_next_steps(
        self,
        state: ResearchControlState,
    ) -> ResearchControlState:
        if self.hypothesis_selector is None:
            return {
                "selection_status": "disabled",
                "selected_hypothesis_steps": [],
            }
        result = await self.hypothesis_selector.select_hypotheses(
            program_id=UUID(state["program_id"]),
            status=("new", "needs_verification", "reviewing", "stale"),
            min_priority_score=0,
            limit=int(state.get("limit", 25)),
        )
        decisions = result.get("decisions") or []
        return {
            "selection_status": "selected",
            "selected_hypothesis_steps": [
                self._selection_step(item) for item in decisions
            ],
        }

    @staticmethod
    def _selection_step(item: dict[str, Any]) -> dict[str, Any]:
        safe_context = item.get("safe_context") or {}
        return {
            "hypothesis_id": str(item.get("hypothesis_id") or ""),
            "next_step": str(item.get("next_step") or "defer"),
            "priority_band": str(item.get("priority_band") or "low"),
            "requires_human_review": bool(item.get("requires_human_review")),
            "reasons": [str(value) for value in item.get("reasons") or []],
            "hypothesis_type": _optional_text(safe_context.get("hypothesis_type")),
            "status": _optional_text(safe_context.get("status")),
            "evidence_count": int(safe_context.get("evidence_count") or 0),
        }

    @staticmethod
    def _input_state(
        request: HypothesisBuildRequest,
        required_projections: tuple[ProjectionKey, ...],
    ) -> ResearchControlState:
        return {
            "program_id": str(request.program_id),
            "result_key": request.result_key,
            "action_id": _optional_uuid(request.action_id),
            "campaign_id": _optional_uuid(request.campaign_id),
            "workflow_id": _optional_uuid(request.workflow_id),
            "workflow_run_id": _optional_uuid(request.workflow_run_id),
            "limit": request.limit,
            "required_projections": [
                {
                    "projection_type": key.projection_type,
                    "projection_name": key.projection_name,
                }
                for key in required_projections
            ],
            "readiness_status": "checking",
        }

    @staticmethod
    def _request(state: ResearchControlState) -> HypothesisBuildRequest:
        return HypothesisBuildRequest(
            program_id=UUID(state["program_id"]),
            result_key=state.get("result_key"),
            action_id=_parse_optional_uuid(state.get("action_id")),
            campaign_id=_parse_optional_uuid(state.get("campaign_id")),
            workflow_id=_parse_optional_uuid(state.get("workflow_id")),
            workflow_run_id=_parse_optional_uuid(state.get("workflow_run_id")),
            limit=int(state.get("limit", 25)),
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        if not thread_id.strip():
            raise ValueError("thread_id is required for checkpointed graph execution")
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _projection_keys(
        state: ResearchControlState,
    ) -> tuple[ProjectionKey, ...]:
        return tuple(
            ProjectionKey(
                projection_type=item["projection_type"],
                projection_name=item["projection_name"],
            )
            for item in state.get("required_projections", ())
        )

    @staticmethod
    def _readiness_state(
        decision: ResearchReadinessDecision,
    ) -> ResearchControlState:
        return {
            "readiness_status": "ready" if decision.ready else "waiting",
            "wait_condition_id": (
                str(decision.wait_condition_id)
                if decision.wait_condition_id is not None
                else None
            ),
            "wait_reason": decision.reason,
            "wait_reason_code": decision.reason_code,
            "wait_condition_type": decision.wait_condition_type,
            "result_set_keys": list(decision.result_set_keys),
        }


def _optional_uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _parse_optional_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
