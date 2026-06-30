"""Terminal pipeline run reporting.

This helper currently coordinates two terminal effects: run-state transition and
action outcome-memory recording. Keep it small. If outcome-memory behavior grows,
move it behind a separate terminal hook instead of adding branching here.
"""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.action_outcomes import ActionOutcomeRecorder
from api.application.contracts import ExecutionStatus, TerminalOutcome
from api.application.ports.orchestration import PipelineRunStatePort

logger = logging.getLogger(__name__)


class RunCompletionReporter:
    """Record terminal run transitions and the current outcome-memory hook."""

    terminal_hook_candidate = "action_outcome_memory"

    def __init__(
        self,
        *,
        run_states: PipelineRunStatePort | None,
        outcomes: ActionOutcomeRecorder | None,
        node_id: str,
    ) -> None:
        self.run_states = run_states
        self.outcomes = outcomes
        self.node_id = node_id
        self.event_name: str | None = None
        self.event_id: UUID | None = None
        self.run_id: UUID | None = None

    def bind_event(
        self,
        *,
        event_name: str | None,
        event_id: UUID | None,
        run_id: UUID | None,
    ) -> None:
        self.event_name = event_name
        self.event_id = event_id
        self.run_id = run_id

    async def mark_run_started(self) -> bool:
        if self.run_id is None or self.run_states is None:
            return True
        return await self.run_states.mark_run_started(
            run_id=self.run_id,
            node_id=self.node_id,
            event_name=self.event_name,
            trigger_event_id=self.event_id,
        )

    async def mark_run_completed(self, *, retry_policy: dict) -> bool:
        return await self.mark_run_finished(
            ExecutionStatus.COMPLETED,
            terminal_outcome=TerminalOutcome.COMPLETED,
            retry_policy=retry_policy,
        )

    async def mark_run_flushing(self) -> bool:
        if self.run_id is None or self.run_states is None:
            return True
        return await self.run_states.mark_run_flushing(run_id=self.run_id)

    async def mark_run_failed(self, error: Exception, *, retry_policy: dict) -> bool:
        return await self.mark_run_finished(
            ExecutionStatus.FAILED,
            error=str(error),
            terminal_outcome=TerminalOutcome.TOOL_FAILED,
            retry_policy=retry_policy,
        )

    async def mark_run_finished(
        self,
        status: ExecutionStatus,
        *,
        retry_policy: dict,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
    ) -> bool:
        if self.run_id is None or self.run_states is None:
            return True

        recorded = await self.run_states.mark_run_finished(
            run_id=self.run_id,
            status=status,
            error=error,
            terminal_outcome=terminal_outcome,
            retry_policy=retry_policy,
        )

        if recorded:
            await self._record_action_outcome()
        return recorded

    async def mark_run_needs_reconcile(self, reason: str) -> None:
        if self.run_id is None or self.run_states is None:
            return

        try:
            await self.run_states.mark_run_needs_reconcile(
                run_id=self.run_id,
                reason=reason,
            )
        except Exception:
            logger.warning("Failed to mark run as needing reconcile", exc_info=True)

    async def _record_action_outcome(self) -> None:
        if self.outcomes is None or self.run_id is None:
            return
        try:
            await self.outcomes.record_finished_run(run_id=self.run_id)
        except Exception:
            logger.warning(
                "Failed to record action outcome memory: run_id=%s",
                self.run_id,
                exc_info=True,
            )
