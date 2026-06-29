"""Application-level wait condition evaluation for agent workflows."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from api.application.projections import (
    ProjectionKey,
    ProjectionReadinessService,
    ProjectionStateReader,
)
from api.application.campaign_lifecycle import CampaignLifecycleDecision

logger = logging.getLogger(__name__)

RESEARCH_WAIT_CONDITION_PREFIXES = ("research:", "mvp-research:")


def is_research_wait_condition_key(condition_key: str) -> bool:
    return condition_key.startswith(RESEARCH_WAIT_CONDITION_PREFIXES)


@dataclass(frozen=True, slots=True)
class AgentWaitCondition:
    condition_type: str
    program_id: Any
    required_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentWaitConditionRecord:
    condition_id: UUID
    condition_type: str
    program_id: Any
    condition_key: str = ""
    workflow_run_id: UUID | None = None
    required_state: dict[str, Any] = field(default_factory=dict)
    deadline_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WaitConditionDecision:
    resolved: bool
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunWaitState:
    run_id: UUID
    status: str
    terminal_outcome: str | None


class AgentWaitConditionRepository(Protocol):
    async def list_pending(
        self,
        *,
        limit: int,
        now: datetime,
    ) -> list[AgentWaitConditionRecord]: ...

    async def list_resume_ready(
        self,
        *,
        limit: int,
    ) -> list[AgentWaitConditionRecord]: ...

    async def mark_resolved(
        self,
        *,
        condition_id: UUID,
        payload: dict[str, Any],
    ) -> bool: ...

    async def mark_timed_out(
        self,
        *,
        condition_id: UUID,
        payload: dict[str, Any],
    ) -> bool: ...


class AgentWorkflowResumer(Protocol):
    async def resume(self, record: AgentWaitConditionRecord) -> None: ...


class AgentResultSetReader(Protocol):
    async def list_result_sets(self, **kwargs) -> list[dict[str, Any]]: ...


class AgentExecutionStateReader(Protocol):
    async def get_run_state(
        self,
        *,
        program_id: Any,
        run_id: UUID,
    ) -> RunWaitState | None: ...


class CampaignLifecycleReader(Protocol):
    async def reconcile_campaign_lifecycle(
        self,
        *,
        program_id: Any,
        campaign_id: UUID,
        now: datetime,
        quiet_window_seconds: float,
    ) -> CampaignLifecycleDecision | None: ...


class CampaignLifecycleReconciler(Protocol):
    async def reconcile_active_campaigns(
        self,
        *,
        now: datetime,
        quiet_window_seconds: float,
        limit: int,
    ) -> int: ...


class AgentWaitConditionEngine:
    def __init__(
        self,
        *,
        projection_reader: ProjectionStateReader,
        result_set_reader: AgentResultSetReader | None = None,
        execution_state_reader: AgentExecutionStateReader | None = None,
        campaign_lifecycle_reader: CampaignLifecycleReader | None = None,
        campaign_quiet_window_seconds: float = 30.0,
    ) -> None:
        self.projection_readiness = ProjectionReadinessService(projection_reader)
        self.result_set_reader = result_set_reader
        self.execution_state_reader = execution_state_reader
        self.campaign_lifecycle_reader = campaign_lifecycle_reader
        self.campaign_quiet_window_seconds = max(
            0.0,
            float(campaign_quiet_window_seconds),
        )

    async def evaluate(self, condition: AgentWaitCondition) -> WaitConditionDecision:
        if condition.condition_type == "tool_run_completed":
            return await self._tool_run_completed(condition)
        if condition.condition_type == "ingestion_completed":
            return await self._ingestion_completed(condition)
        if condition.condition_type == "new_facts_available":
            return await self._result_sets_ready(condition)
        if condition.condition_type == "projections_ready":
            return await self._projections_ready(condition)
        if condition.condition_type == "campaign_quiescent":
            return await self._campaign_quiescent(condition)
        return WaitConditionDecision(
            resolved=False,
            reason="unsupported_wait_condition",
        )

    async def _campaign_quiescent(
        self,
        condition: AgentWaitCondition,
    ) -> WaitConditionDecision:
        if self.campaign_lifecycle_reader is None:
            return WaitConditionDecision(
                resolved=False,
                reason="campaign_lifecycle_reader_unavailable",
            )
        value = condition.required_state.get("campaign_id")
        if value is None:
            return WaitConditionDecision(
                resolved=False,
                reason="campaign_id_required",
            )
        try:
            campaign_id = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            return WaitConditionDecision(
                resolved=False,
                reason="invalid_campaign_id",
            )
        decision = await self.campaign_lifecycle_reader.reconcile_campaign_lifecycle(
            program_id=condition.program_id,
            campaign_id=campaign_id,
            now=datetime.now(timezone.utc),
            quiet_window_seconds=self.campaign_quiet_window_seconds,
        )
        if decision is None:
            return WaitConditionDecision(
                resolved=False,
                reason="campaign_not_found",
                payload={"campaign_id": str(campaign_id)},
            )
        return WaitConditionDecision(
            resolved=decision.quiescent,
            reason=decision.reason,
            payload={
                "campaign_id": str(campaign_id),
                "status": decision.status,
                "quiet_for_seconds": decision.quiet_for_seconds,
            },
        )

    async def _tool_run_completed(
        self,
        condition: AgentWaitCondition,
    ) -> WaitConditionDecision:
        state = await self._run_state(condition)
        if isinstance(state, WaitConditionDecision):
            return state
        terminal = state.status in {"completed", "failed", "dead", "cancelled"}
        return WaitConditionDecision(
            resolved=terminal,
            reason="tool_run_terminal" if terminal else "tool_run_not_terminal",
            payload=self._run_payload(state),
        )

    async def _ingestion_completed(
        self,
        condition: AgentWaitCondition,
    ) -> WaitConditionDecision:
        state = await self._run_state(condition)
        if isinstance(state, WaitConditionDecision):
            return state
        completed = state.status == "completed"
        return WaitConditionDecision(
            resolved=completed,
            reason="ingestion_completed" if completed else "ingestion_not_completed",
            payload=self._run_payload(state),
        )

    async def _run_state(
        self,
        condition: AgentWaitCondition,
    ) -> RunWaitState | WaitConditionDecision:
        if self.execution_state_reader is None:
            return WaitConditionDecision(
                resolved=False,
                reason="execution_state_reader_unavailable",
            )
        value = condition.required_state.get("run_id")
        if value is None:
            return WaitConditionDecision(
                resolved=False,
                reason="run_id_required",
            )
        try:
            run_id = value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError):
            return WaitConditionDecision(
                resolved=False,
                reason="invalid_run_id",
            )
        state = await self.execution_state_reader.get_run_state(
            program_id=condition.program_id,
            run_id=run_id,
        )
        if state is None:
            return WaitConditionDecision(
                resolved=False,
                reason="run_not_found",
                payload={"run_id": str(run_id)},
            )
        return state

    @staticmethod
    def _run_payload(state: RunWaitState) -> dict[str, str | None]:
        return {
            "run_id": str(state.run_id),
            "status": state.status,
            "terminal_outcome": state.terminal_outcome,
        }

    async def _projections_ready(
        self,
        condition: AgentWaitCondition,
    ) -> WaitConditionDecision:
        required = self._projection_keys(condition.required_state)
        readiness = await self.projection_readiness.evaluate(
            program_id=condition.program_id,
            required=required,
        )
        payload = {
            "missing": [self._projection_key_payload(key) for key in readiness.missing],
            "lagging": [self._projection_key_payload(key) for key in readiness.lagging],
            "failed": [self._projection_key_payload(key) for key in readiness.failed],
        }
        if readiness.ready:
            return WaitConditionDecision(
                resolved=True,
                reason="projections_ready",
                payload=payload,
            )
        return WaitConditionDecision(
            resolved=False,
            reason="projections_not_ready",
            payload=payload,
        )

    async def _result_sets_ready(
        self,
        condition: AgentWaitCondition,
    ) -> WaitConditionDecision:
        if self.result_set_reader is None:
            return WaitConditionDecision(
                resolved=False,
                reason="result_set_reader_unavailable",
                payload={"result_set_keys": []},
            )
        selectors = {}
        if condition.required_state.get("result_key") is not None:
            selectors["result_key"] = str(condition.required_state["result_key"])
        for key in (
            "action_id",
            "campaign_id",
            "workflow_id",
            "workflow_run_id",
        ):
            value = condition.required_state.get(key)
            if value is not None:
                selectors[key] = value if isinstance(value, UUID) else UUID(str(value))
        rows = await self.result_set_reader.list_result_sets(
            program_id=condition.program_id,
            limit=1,
            **selectors,
        )
        keys = [str(row["result_key"]) for row in rows if row.get("result_key")]
        return WaitConditionDecision(
            resolved=bool(keys),
            reason="result_sets_ready" if keys else "result_sets_not_ready",
            payload={"result_set_keys": keys},
        )

    @staticmethod
    def _projection_keys(required_state: dict[str, Any]) -> tuple[ProjectionKey, ...]:
        return tuple(
            ProjectionKey(
                projection_type=str(item["projection_type"]),
                projection_name=str(item["projection_name"]),
            )
            for item in required_state.get("projections", ())
        )

    @staticmethod
    def _projection_key_payload(key: ProjectionKey) -> dict[str, str]:
        return {
            "projection_type": key.projection_type,
            "projection_name": key.projection_name,
        }


class AgentWaitConditionProcessor:
    def __init__(
        self,
        *,
        store: AgentWaitConditionRepository,
        engine: AgentWaitConditionEngine,
        workflow_resumer: AgentWorkflowResumer | None = None,
        campaign_lifecycle_reconciler: CampaignLifecycleReconciler | None = None,
        campaign_quiet_window_seconds: float = 30.0,
        sweep_interval_seconds: float = 5.0,
    ) -> None:
        self.store = store
        self.engine = engine
        self.workflow_resumer = workflow_resumer
        self.campaign_lifecycle_reconciler = campaign_lifecycle_reconciler
        self.campaign_quiet_window_seconds = max(
            0.0,
            float(campaign_quiet_window_seconds),
        )
        self.sweep_interval_seconds = max(0.01, float(sweep_interval_seconds))
        self._stop_event = asyncio.Event()
        self._run_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._run_task = asyncio.create_task(
            self.run(),
            name="agent-wait-condition-processor",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._run_task is not None:
            self._run_task.cancel()
            await asyncio.gather(self._run_task, return_exceptions=True)
        self._run_task = None

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.process_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Agent wait-condition sweep failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.sweep_interval_seconds,
                )
            except TimeoutError:
                pass

    async def process_once(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        if self.campaign_lifecycle_reconciler is not None:
            await self.campaign_lifecycle_reconciler.reconcile_active_campaigns(
                now=now,
                quiet_window_seconds=self.campaign_quiet_window_seconds,
                limit=max(1, limit),
            )
        records = await self.store.list_pending(limit=max(1, limit), now=now)
        transitions = 0

        for record in records:
            if record.deadline_at is not None and record.deadline_at <= now:
                changed = await self.store.mark_timed_out(
                    condition_id=record.condition_id,
                    payload={"reason": "deadline_elapsed"},
                )
                transitions += int(changed)
                continue

            decision = await self.engine.evaluate(
                AgentWaitCondition(
                    condition_type=record.condition_type,
                    program_id=record.program_id,
                    required_state=record.required_state,
                )
            )
            if decision.resolved:
                changed = await self.store.mark_resolved(
                    condition_id=record.condition_id,
                    payload=decision.payload,
                )
                if changed:
                    transitions += 1
                    if (
                        self.workflow_resumer is not None
                        and record.workflow_run_id is not None
                        and is_research_wait_condition_key(record.condition_key)
                    ):
                        await self.workflow_resumer.resume(record)

        if self.workflow_resumer is not None:
            resume_records = await self.store.list_resume_ready(
                limit=max(1, limit),
            )
            for record in resume_records:
                if (
                    record.workflow_run_id is not None
                    and is_research_wait_condition_key(record.condition_key)
                ):
                    await self.workflow_resumer.resume(record)

        return transitions
