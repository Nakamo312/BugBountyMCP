"""Narrow orchestration ports used by application code.

There is no all-in-one orchestration facade. Application modules depend on
scenario contracts instead of a one-object-knows-everything store.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from api.application.contracts import (
    EventDispatchRecord,
    EventEnvelope,
    ExecutionStatus,
    NodeRunClaim,
    NodeRunClaimRequest,
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
    async def claim_node_run(self, request: NodeRunClaimRequest) -> NodeRunClaim:
        ...


class ScheduledLeasePort(Protocol):
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


class ScheduledRecoveryPort(Protocol):
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


class ScheduledRetryPort(Protocol):
    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
        max_requeues_per_node: int | None = None,
        retry_jitter_seconds: float = 0.0,
    ) -> int:
        ...

class EventRecorderPort(Protocol):
    async def record_event(self, envelope: EventEnvelope) -> None:
        ...


class EventDispatchLeasePort(Protocol):
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
