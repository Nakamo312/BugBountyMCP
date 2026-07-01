"""Session boundary for approval state transitions."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import EventEnvelope, PolicyDecision, ResolvedActionCommand
from api.infrastructure.orchestration.approval_transactions import (
    approve_and_create_queued_job_in_session,
    reject_action_in_session,
)
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore
from api.infrastructure.orchestration.dispatch_writer import DispatchWriterStore


class ApprovalDecisionStore:
    """Durable session boundary for approval decisions and approval-time queueing."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        campaigns: CampaignWriteStore,
        dispatches: DispatchWriterStore,
    ):
        self.session_factory = session_factory
        self.campaigns = campaigns
        self.dispatches = dispatches

    async def approve_and_create_queued_job(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
    ) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            approved = await approve_and_create_queued_job_in_session(
                session,
                campaigns=self.campaigns,
                dispatches=self.dispatches,
                action=action,
                decision=decision,
                envelope=envelope,
                now=now,
            )
            if approved:
                await session.commit()
            return approved

    async def reject_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> bool:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            rejected = await reject_action_in_session(
                session,
                action=action,
                decision=decision,
                now=now,
            )
            if rejected:
                await session.commit()
            return rejected
