"""In-transaction campaign write primitives for action execution flows."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.application.campaign_lifecycle import TERMINAL_CAMPAIGN_STATUSES
from api.application.contracts import ResolvedActionCommand
from api.config import Settings
from api.infrastructure.adapters.orm import campaigns


class CampaignWriteStore:
    """Campaign write primitive used inside caller-owned transactions."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    async def upsert_campaign(self, session, action: ResolvedActionCommand, now: datetime) -> None:
        stmt = pg_insert(campaigns).values(
            id=action.campaign_id,
            program_id=action.program_id,
            correlation_id=action.correlation_id,
            workflow_id=action.workflow_id,
            status="created",
            metadata=action.metadata,
            max_runs=self.settings.CAMPAIGN_MAX_RUNS,
            max_targets=self.settings.CAMPAIGN_MAX_TARGETS,
            runs_consumed=0,
            targets_consumed=0,
            token_capacity=self.settings.CAMPAIGN_TOKEN_CAPACITY,
            tokens_available=self.settings.CAMPAIGN_TOKEN_CAPACITY,
            token_refill_per_second=self.settings.CAMPAIGN_TOKEN_REFILL_PER_SECOND,
            tokens_refilled_at=now,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[campaigns.c.id],
            set_={
                "updated_at": now,
                "correlation_id": action.correlation_id,
                "workflow_id": action.workflow_id,
            },
        )
        await session.execute(stmt)

    async def activate_campaign(
        self,
        session,
        *,
        campaign_id: uuid.UUID,
        status: str,
        now: datetime,
    ) -> None:
        await session.execute(
            update(campaigns)
            .where(
                campaigns.c.id == campaign_id,
                campaigns.c.status.notin_(TERMINAL_CAMPAIGN_STATUSES),
            )
            .values(status=status, updated_at=now)
        )
