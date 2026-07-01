"""Session boundary for allowed-action queue writes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import EventEnvelope, PolicyDecision, ResolvedActionCommand
from api.infrastructure.orchestration.action_command_transactions import create_allowed_action_in_session
from api.infrastructure.orchestration.action_submission_conflicts import (
    raise_submission_conflict_for_duplicate_action,
)
from api.infrastructure.orchestration.campaign_write_store import CampaignWriteStore
from api.infrastructure.orchestration.dispatch_writer import DispatchWriterStore


class AllowedActionQueueStore:
    """Durable session boundary for allowed action state and outbox queueing."""

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

    async def create_allowed_action(
        self,
        action: ResolvedActionCommand,
        decision: PolicyDecision,
        envelope: EventEnvelope,
        *,
        scope_id: uuid.UUID,
    ) -> None:
        """Persist allowed action state and its outbox delivery atomically."""
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            try:
                await create_allowed_action_in_session(
                    session,
                    campaigns=self.campaigns,
                    dispatches=self.dispatches,
                    action=action,
                    decision=decision,
                    envelope=envelope,
                    scope_id=scope_id,
                    now=now,
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise_submission_conflict_for_duplicate_action(action.action_id, exc)
                raise
            except Exception:
                await session.rollback()
                raise
