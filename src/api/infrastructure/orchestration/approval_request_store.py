"""Session boundary for approval request reads."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ActionRequest
from api.infrastructure.orchestration.approval_transactions import (
    select_action_for_approval,
    select_latest_scope_id,
)


class ApprovalRequestStore:
    """Read pending approval state needed by approval workflows."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def get_action_for_approval(
        self,
        action_id: uuid.UUID,
    ) -> tuple[ActionRequest | None, str | None]:
        async with self.session_factory() as session:
            return await select_action_for_approval(session, action_id=action_id)

    async def get_scope_id(self, action_id: uuid.UUID) -> uuid.UUID | None:
        async with self.session_factory() as session:
            return await select_latest_scope_id(session, action_id=action_id)
