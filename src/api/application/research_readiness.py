"""Research readiness gate connecting durable waits to the research pass."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from api.application.agent_wait_conditions import (
    AgentWaitCondition,
    AgentWaitConditionEngine,
    WaitConditionDecision,
)
from api.application.hypotheses import HypothesisBuildRequest
from api.application.projections import ProjectionKey


class ResearchReadinessReason:
    READY = "research_inputs_ready"
    PROJECTIONS_NOT_READY = "projections_not_ready"
    PROJECTION_FAILED = "projection_failed"
    PROJECTION_MISSING = "projection_missing"
    PROJECTION_LAGGING = "projection_lagging"
    RESULT_SETS_NOT_READY = "result_sets_not_ready"
    RESULT_SET_READER_UNAVAILABLE = "result_set_reader_unavailable"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_TERMINAL = "workflow_terminal"
    CAMPAIGN_NOT_READY = "campaign_not_ready"
    WAIT_DEADLINE_ELAPSED = "wait_deadline_elapsed"
    DURABLE_WAIT_REQUIRES_WORKFLOW_RUN = "durable_wait_requires_workflow_run"
    UNSUPPORTED_WAIT_CONDITION = "unsupported_wait_condition"


class WaitConditionStore(Protocol):
    async def create_wait_condition(self, **kwargs) -> UUID | None: ...


class WorkflowRuntime(Protocol):
    async def pause(self, **kwargs): ...

    async def resume(self, **kwargs): ...


@dataclass(frozen=True, slots=True)
class ResearchReadinessDecision:
    ready: bool
    reason: str
    wait_condition_id: UUID | None = None
    payload: dict[str, Any] | None = None
    result_set_keys: tuple[str, ...] = ()
    reason_code: str | None = None
    wait_condition_type: str | None = None

    def __post_init__(self) -> None:
        if self.reason_code is None:
            object.__setattr__(self, "reason_code", self.reason)


class ResearchReadinessGate:
    def __init__(
        self,
        *,
        wait_engine: AgentWaitConditionEngine,
        protocol_store: WaitConditionStore,
        workflow_runtime: WorkflowRuntime | None = None,
    ) -> None:
        self.wait_engine = wait_engine
        self.protocol_store = protocol_store
        self.workflow_runtime = workflow_runtime

    async def evaluate(
        self,
        request: HypothesisBuildRequest,
        *,
        required_projections: tuple[ProjectionKey, ...],
    ) -> ResearchReadinessDecision:
        if required_projections:
            required_state = {
                "projections": [
                    {
                        "projection_type": key.projection_type,
                        "projection_name": key.projection_name,
                    }
                    for key in required_projections
                ]
            }
            projection_decision = await self.wait_engine.evaluate(
                AgentWaitCondition(
                    condition_type="projections_ready",
                    program_id=request.program_id,
                    required_state=required_state,
                )
            )
            if not projection_decision.resolved:
                return await self._persist_wait(
                    request=request,
                    condition_type="projections_ready",
                    required_state=required_state,
                    decision=projection_decision,
                    reason_code=self._reason_code(
                        "projections_ready",
                        projection_decision,
                    ),
                )

        result_state = self._result_set_state(request)
        result_decision = await self.wait_engine.evaluate(
            AgentWaitCondition(
                condition_type="new_facts_available",
                program_id=request.program_id,
                required_state=result_state,
            )
        )
        if not result_decision.resolved:
            return await self._persist_wait(
                request=request,
                condition_type="new_facts_available",
                required_state=result_state,
                decision=result_decision,
                reason_code=self._reason_code(
                    "new_facts_available",
                    result_decision,
                ),
            )
        ready = ResearchReadinessDecision(
            ready=True,
            reason="research_inputs_ready",
            reason_code=ResearchReadinessReason.READY,
            payload=result_decision.payload,
            result_set_keys=tuple(result_decision.payload.get("result_set_keys", ())),
        )
        if self.workflow_runtime is not None and request.workflow_run_id is not None:
            await self.workflow_runtime.resume(
                run_id=request.workflow_run_id,
                checkpoint_ref=f"langgraph:{request.workflow_run_id}",
            )
        return ready

    async def _persist_wait(
        self,
        *,
        request: HypothesisBuildRequest,
        condition_type: str,
        required_state: dict[str, Any],
        decision: WaitConditionDecision,
        reason_code: str,
    ) -> ResearchReadinessDecision:
        if request.workflow_run_id is None:
            raise ValueError(ResearchReadinessReason.DURABLE_WAIT_REQUIRES_WORKFLOW_RUN)
        condition_id = await self.protocol_store.create_wait_condition(
            workflow_run_id=request.workflow_run_id,
            program_id=request.program_id,
            campaign_id=request.campaign_id,
            correlation_id=None,
            condition_type=condition_type,
            condition_key=self._condition_key(request, condition_type),
            required_state=required_state,
        )
        if self.workflow_runtime is not None:
            await self.workflow_runtime.pause(
                run_id=request.workflow_run_id,
                checkpoint_ref=f"langgraph:{request.workflow_run_id}",
                current_node="wait_for_readiness",
                wait_condition_id=condition_id,
            )
        return ResearchReadinessDecision(
            ready=False,
            reason=decision.reason,
            reason_code=reason_code,
            wait_condition_id=condition_id,
            wait_condition_type=condition_type,
            payload=decision.payload,
        )

    @staticmethod
    def _result_set_state(request: HypothesisBuildRequest) -> dict[str, str]:
        return {
            key: str(value)
            for key, value in (
                ("result_key", request.result_key),
                ("action_id", request.action_id),
                ("campaign_id", request.campaign_id),
                ("workflow_id", request.workflow_id),
                ("workflow_run_id", request.workflow_run_id),
            )
            if value is not None
        }

    @staticmethod
    def _condition_key(
        request: HypothesisBuildRequest,
        condition_type: str,
    ) -> str:
        identity = ":".join(
            str(value or "")
            for value in (
                request.program_id,
                request.result_key,
                request.action_id,
                request.campaign_id,
                request.workflow_id,
                request.workflow_run_id,
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return f"research:{condition_type}:{digest}"

    @staticmethod
    def _reason_code(
        condition_type: str,
        decision: WaitConditionDecision,
    ) -> str:
        if decision.resolved:
            return ResearchReadinessReason.READY
        if condition_type == "projections_ready":
            payload = decision.payload or {}
            if payload.get("failed"):
                return ResearchReadinessReason.PROJECTION_FAILED
            if payload.get("missing"):
                return ResearchReadinessReason.PROJECTION_MISSING
            if payload.get("lagging"):
                return ResearchReadinessReason.PROJECTION_LAGGING
            if decision.reason == "unsupported_wait_condition":
                return ResearchReadinessReason.UNSUPPORTED_WAIT_CONDITION
            return ResearchReadinessReason.PROJECTIONS_NOT_READY
        if condition_type == "new_facts_available":
            if decision.reason == "result_set_reader_unavailable":
                return ResearchReadinessReason.RESULT_SET_READER_UNAVAILABLE
            if decision.reason == "workflow_cancelled":
                return ResearchReadinessReason.WORKFLOW_CANCELLED
            if decision.reason.endswith("_terminal"):
                return ResearchReadinessReason.WORKFLOW_TERMINAL
            if decision.reason == "deadline_elapsed":
                return ResearchReadinessReason.WAIT_DEADLINE_ELAPSED
            return ResearchReadinessReason.RESULT_SETS_NOT_READY
        if decision.reason == "campaign_not_found" or decision.reason.startswith("campaign_"):
            return ResearchReadinessReason.CAMPAIGN_NOT_READY
        return decision.reason or ResearchReadinessReason.UNSUPPORTED_WAIT_CONDITION
