"""Narrow pipeline adapter over scenario-owned orchestration stores."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from api.application.contracts import (
    ExecutionMode,
    ExecutionStatus,
    NodeRunClaim,
    ScheduledNodeRun,
    TerminalOutcome,
)
from api.infrastructure.orchestration.run_claim_store import RunClaimStore
from api.infrastructure.orchestration.run_state_store import RunStateStore
from api.infrastructure.orchestration.scheduled_work_store import ScheduledWorkStore


class PipelineOrchestrationStore:
    """Combined pipeline port for node claim, scheduled queue, and run state."""

    def __init__(
        self,
        *,
        run_claims: RunClaimStore,
        scheduled_work: ScheduledWorkStore,
        run_states: RunStateStore,
    ) -> None:
        self.run_claims = run_claims
        self.scheduled_work = scheduled_work
        self.run_states = run_states

    async def claim_node_run(
        self,
        *,
        claim_key: str,
        job_id: uuid.UUID,
        program_id: uuid.UUID,
        node_id: str,
        event_name: str,
        trigger_event_id: uuid.UUID,
        input_fingerprint: str,
        target_fingerprint: str,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        next_run_at: datetime | None = None,
        target_count: int | None = None,
        run_payload: Mapping[str, Any] | None = None,
        work_key: str | None = None,
        coalesced_trigger: Mapping[str, Any] | None = None,
        retry_policy: dict | None = None,
        campaign_id: uuid.UUID | None = None,
        expansion_depth: int = 0,
        max_expansion_depth: int | None = None,
        cooldown_seconds: int | float = 0,
        token_cost: int | float = 1,
    ) -> NodeRunClaim:
        return await self.run_claims.claim_node_run(
            claim_key=claim_key,
            job_id=job_id,
            program_id=program_id,
            node_id=node_id,
            event_name=event_name,
            trigger_event_id=trigger_event_id,
            input_fingerprint=input_fingerprint,
            target_fingerprint=target_fingerprint,
            execution_mode=execution_mode,
            next_run_at=next_run_at,
            target_count=target_count,
            run_payload=run_payload,
            work_key=work_key,
            coalesced_trigger=coalesced_trigger,
            retry_policy=retry_policy,
            campaign_id=campaign_id,
            expansion_depth=expansion_depth,
            max_expansion_depth=max_expansion_depth,
            cooldown_seconds=cooldown_seconds,
            token_cost=token_cost,
        )

    async def count_scheduled_active_runs_by_node(self) -> dict[str, int]:
        return await self.scheduled_work.count_scheduled_active_runs_by_node()

    async def lease_ready_scheduled_node_runs(
        self,
        *,
        node_limits: Mapping[str, int],
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> list[ScheduledNodeRun]:
        return await self.scheduled_work.lease_ready_scheduled_node_runs(
            node_limits=node_limits,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )

    async def recover_stale_leases(self, *, now: datetime | None = None) -> int:
        return await self.scheduled_work.recover_stale_leases(now=now)

    async def fail_stale_scheduled_active_runs(
        self,
        *,
        running_timeout_seconds: int,
        flushing_timeout_seconds: int,
        now: datetime | None = None,
    ) -> int:
        return await self.scheduled_work.fail_stale_scheduled_active_runs(
            running_timeout_seconds=running_timeout_seconds,
            flushing_timeout_seconds=flushing_timeout_seconds,
            now=now,
        )

    async def requeue_retryable_node_runs(
        self,
        *,
        retry_policies: dict[str, dict],
        max_requeues_per_node: int | None = None,
        retry_jitter_seconds: float = 0.0,
    ) -> int:
        return await self.scheduled_work.requeue_retryable_node_runs(
            retry_policies=retry_policies,
            max_requeues_per_node=max_requeues_per_node,
            retry_jitter_seconds=retry_jitter_seconds,
        )

    async def mark_run_started(
        self,
        *,
        run_id: uuid.UUID,
        node_id: str,
        event_name: str | None,
        trigger_event_id: uuid.UUID | None = None,
    ) -> bool:
        return await self.run_states.mark_run_started(
            run_id=run_id,
            node_id=node_id,
            event_name=event_name,
            trigger_event_id=trigger_event_id,
        )

    async def mark_run_flushing(self, *, run_id: uuid.UUID) -> bool:
        return await self.run_states.mark_run_flushing(run_id=run_id)

    async def mark_run_finished(
        self,
        *,
        run_id: uuid.UUID,
        status: ExecutionStatus,
        error: str | None = None,
        terminal_outcome: TerminalOutcome | None = None,
        retry_policy: dict | None = None,
    ) -> bool:
        return await self.run_states.mark_run_finished(
            run_id=run_id,
            status=status,
            error=error,
            terminal_outcome=terminal_outcome,
            retry_policy=retry_policy,
        )

    async def mark_run_needs_reconcile(self, *, run_id: uuid.UUID, reason: str) -> None:
        await self.run_states.mark_run_needs_reconcile(run_id=run_id, reason=reason)

    async def clear_run_reconcile(self, *, run_id: uuid.UUID) -> None:
        await self.run_states.clear_run_reconcile(run_id=run_id)
