"""Narrow orchestration ports used by application code.

The compatibility OrchestrationStore still exists in infrastructure, but application
modules should depend on these scenario contracts instead of the whole facade.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from api.application.contracts import (
    EventDispatchRecord,
    EventEnvelope,
    ExecutionMode,
    ExecutionStatus,
    NodeRunClaim,
    ScheduledNodeRun,
    TerminalOutcome,
)


class PipelineRunStatePort(Protocol):
    async def mark_run_started(
        self,
        *,
        run_id: UUID,
        node_id: str,
        event_name: str | None,
        trigger_event_id: UUID | None = None,
    ) -> bool:
        ...

    async def mark_run_flushing(self, *, run_id: UUID) -> bool:
        ...

    async def mark_run_finished(
        self,
        *,
        run_id: UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> bool:
        ...

    async def mark_run_needs_reconcile(self, *, run_id: UUID, reason: str) -> None:
        ...

    async def clear_run_reconcile(self, *, run_id: UUID) -> None:
        ...


class NodeRunClaimPort(Protocol):
    async def claim_node_run(
        self,
        *,
        claim_key: str,
        job_id: UUID,
        program_id: UUID,
        node_id: str,
        event_name: str,
        trigger_event_id: UUID,
        input_fingerprint: str,
        target_fingerprint: str,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        next_run_at: datetime | None = None,
        target_count: int | None = None,
        run_payload: Mapping[str, Any] | None = None,
        work_key: str | None = None,
        coalesced_trigger: Mapping[str, Any] | None = None,
        retry_policy: dict | None = None,
        campaign_id: UUID | None = None,
        expansion_depth: int = 0,
        max_expansion_depth: int | None = None,
        cooldown_seconds: int | float = 0,
        token_cost: int | float = 1,
    ) -> NodeRunClaim:
        ...


class ScheduledRunStorePort(Protocol):
    async def count_scheduled_active_runs_by_node(self) -> dict[str, int]:
        ...

    async def lease_ready_scheduled_node_runs(
        self,
        *,
        node_limits: Mapping[str, int],
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> list[ScheduledNodeRun]:
        ...

    async def recover_stale_leases(self, *, now: datetime | None = None) -> int:
        ...

    async def fail_stale_scheduled_active_runs(
        self,
        *,
        running_timeout_seconds: int,
        flushing_timeout_seconds: int,
        now: datetime | None = None,
    ) -> int:
        ...

    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
        max_requeues_per_node: int | None = None,
        retry_jitter_seconds: float = 0.0,
    ) -> int:
        ...

    async def mark_run_finished(
        self,
        *,
        run_id: UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> bool:
        ...


class EventRecorderPort(Protocol):
    async def record_event(self, envelope: EventEnvelope) -> None:
        ...


class EventDispatchStorePort(Protocol):
    async def claim_dispatches(
        self,
        *,
        destination: str,
        dispatcher_id: str,
        batch_size: int,
        lease_ttl_seconds: int,
    ) -> list[EventDispatchRecord]:
        ...

    async def mark_sent(self, *, dispatch_id: UUID, dispatcher_id: str) -> bool:
        ...

    async def mark_failed(
        self,
        *,
        dispatch_id: UUID,
        dispatcher_id: str,
        error: str,
        current_attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> bool:
        ...


class PipelineOrchestrationStorePort(
    NodeRunClaimPort,
    ScheduledRunStorePort,
    PipelineRunStatePort,
    Protocol,
):
    """Combined pipeline port used only where claim, schedule, and run state meet."""
