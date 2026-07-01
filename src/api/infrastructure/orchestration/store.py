"""Compatibility facade over scenario-owned orchestration stores."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.campaign_lifecycle import CampaignActivityState, CampaignLifecycleDecision
from api.application.contracts import (
    ActionArtifactReference,
    ActionEventRecord,
    ActionRecord,
    ActionRequest,
    ActionRunResult,
    ResolvedActionCommand,
    EventDispatchRecord,
    EventEnvelope,
    ExecutionMode,
    ExecutionStatus,
    NodeRunClaim,
    PolicyDecision,
    ScheduledNodeRun,
    TerminalOutcome,
)
from api.config import Settings
from api.infrastructure.orchestration.action_command_store import ActionCommandStore
from api.infrastructure.orchestration.action_read_store import ActionReadStore
from api.infrastructure.orchestration.approval_store import ApprovalStore
from api.infrastructure.orchestration.campaign_state_store import CampaignStateStore
from api.infrastructure.orchestration.dispatch_store import DispatchStore
from api.infrastructure.orchestration.event_store import EventStore
from api.infrastructure.orchestration.run_claim_store import RunClaimStore
from api.infrastructure.orchestration.run_state_store import RunStateStore
from api.infrastructure.orchestration.scheduled_work_store import ScheduledWorkStore


class OrchestrationStore:
    """Deprecated compatibility facade for orchestration persistence scenarios.

    New application code must depend on scenario-owned stores/ports directly.
    Adding methods here keeps the old one-object-knows-everything model alive.
    """

    deprecated_compatibility_facade = True

    def __init__(
        self,
        session_factory: async_sessionmaker,
        settings: Settings | None = None,
    ):
        self.session_factory = session_factory
        self.settings = settings or Settings()
        self.campaigns = CampaignStateStore(session_factory, self.settings)
        self.dispatches = DispatchStore(session_factory, self.settings)
        self.scheduled_work = ScheduledWorkStore(session_factory)
        self.events = EventStore(session_factory)
        self.run_claims = RunClaimStore(session_factory)
        self.run_states = RunStateStore(session_factory)
        self.action_reads = ActionReadStore(session_factory)
        self.action_commands = ActionCommandStore(
            session_factory,
            campaigns=self.campaigns,
            dispatches=self.dispatches,
        )
        self.approvals = ApprovalStore(
            session_factory,
            campaigns=self.campaigns,
            dispatches=self.dispatches,
        )

    async def get_campaign_activity(
        self,
        *,
        program_id: uuid.UUID,
        campaign_id: uuid.UUID,
    ) -> CampaignActivityState | None:
        return await self.campaigns.get_campaign_activity(
            program_id=program_id,
            campaign_id=campaign_id,
        )

    async def reconcile_campaign_lifecycle(
        self,
        *,
        program_id: uuid.UUID,
        campaign_id: uuid.UUID,
        now: datetime,
        quiet_window_seconds: float,
    ) -> CampaignLifecycleDecision | None:
        return await self.campaigns.reconcile_campaign_lifecycle(
            program_id=program_id,
            campaign_id=campaign_id,
            now=now,
            quiet_window_seconds=quiet_window_seconds,
        )

    async def reconcile_active_campaigns(
        self,
        *,
        now: datetime,
        quiet_window_seconds: float,
        limit: int,
    ) -> int:
        return await self.campaigns.reconcile_active_campaigns(
            now=now,
            quiet_window_seconds=quiet_window_seconds,
            limit=limit,
        )

    async def mark_campaign_terminal(self, *, campaign_id: uuid.UUID, status: str) -> bool:
        return await self.campaigns.mark_campaign_terminal(
            campaign_id=campaign_id,
            status=status,
        )

    async def claim_dispatches(
        self,
        *,
        destination: str,
        dispatcher_id: str,
        batch_size: int,
        lease_ttl_seconds: int,
    ) -> list[EventDispatchRecord]:
        return await self.dispatches.claim_dispatches(
            destination=destination,
            dispatcher_id=dispatcher_id,
            batch_size=batch_size,
            lease_ttl_seconds=lease_ttl_seconds,
        )

    async def mark_sent(self, *, dispatch_id: uuid.UUID, dispatcher_id: str) -> bool:
        return await self.dispatches.mark_sent(
            dispatch_id=dispatch_id,
            dispatcher_id=dispatcher_id,
        )

    async def mark_failed(
        self,
        *,
        dispatch_id: uuid.UUID,
        dispatcher_id: str,
        error: str,
        current_attempts: int,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> bool:
        return await self.dispatches.mark_failed(
            dispatch_id=dispatch_id,
            dispatcher_id=dispatcher_id,
            error=error,
            current_attempts=current_attempts,
            max_attempts=max_attempts,
            retry_delay_seconds=retry_delay_seconds,
        )

    async def list_actions(
        self,
        *,
        status: str | None = None,
        program_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionRecord]:
        return await self.action_reads.list_actions(
            status=status,
            program_id=program_id,
            limit=limit,
            offset=offset,
        )

    async def get_action(self, action_id: uuid.UUID) -> ActionRecord | None:
        return await self.action_reads.get_action(action_id)

    async def list_action_events(
        self,
        action_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ActionEventRecord]:
        return await self.action_reads.list_action_events(action_id, limit=limit, offset=offset)

    async def list_action_runs(self, action_id: uuid.UUID) -> list[ActionRunResult]:
        return await self.action_reads.list_action_runs(action_id)

    async def list_action_artifacts(self, action_id: uuid.UUID) -> list[ActionArtifactReference]:
        return await self.action_reads.list_action_artifacts(action_id)

    async def get_action_for_approval(
        self,
        action_id: uuid.UUID,
    ) -> tuple[ActionRequest | None, str | None]:
        return await self.approvals.get_action_for_approval(action_id)

    async def record_policy_result(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> uuid.UUID:
        return await self.action_commands.record_policy_result(action, decision)

    async def create_allowed_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: uuid.UUID,
    ) -> None:
        await self.action_commands.create_allowed_action(
            action,
            decision,
            envelope,
            scope_id=scope_id,
        )

    async def get_scope_id(self, action_id: uuid.UUID) -> uuid.UUID | None:
        return await self.action_commands.get_scope_id(action_id)

    async def create_queued_job(self, action: ResolvedActionCommand, envelope: EventEnvelope) -> None:
        await self.action_commands.create_queued_job(action, envelope)

    async def approve_and_create_queued_job(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
    ) -> bool:
        return await self.approvals.approve_and_create_queued_job(action, decision, envelope)

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

    async def mark_run_needs_reconcile(self, *, run_id: uuid.UUID, reason: str) -> None:
        await self.run_states.mark_run_needs_reconcile(run_id=run_id, reason=reason)

    async def clear_run_reconcile(self, *, run_id: uuid.UUID) -> None:
        await self.run_states.clear_run_reconcile(run_id=run_id)

    async def reject_action(self, action: ResolvedActionCommand, decision: PolicyDecision) -> bool:
        return await self.approvals.reject_action(action, decision)

    async def record_event(self, envelope: EventEnvelope) -> None:
        await self.events.record_event(envelope)

