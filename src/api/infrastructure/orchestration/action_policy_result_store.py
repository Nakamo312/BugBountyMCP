"""Session boundary for terminal or approval-required action policy results."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import PolicyDecision, ResolvedActionCommand
from api.infrastructure.orchestration.action_command_transactions import record_policy_result_in_session
from api.infrastructure.orchestration.action_submission_conflicts import (
    raise_submission_conflict_for_duplicate_action,
)
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore


class ActionPolicyResultStore:
    """Durable session boundary for non-queued action policy results."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        campaigns: CampaignWriteStore,
    ):
        self.session_factory = session_factory
        self.campaigns = campaigns

    async def record_policy_result(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
    ) -> uuid.UUID:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            try:
                scope_id = await record_policy_result_in_session(
                    session,
                    campaigns=self.campaigns,
                    action=action,
                    decision=decision,
                    now=now,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise_submission_conflict_for_duplicate_action(action.action_id, exc)
                raise
        return scope_id
