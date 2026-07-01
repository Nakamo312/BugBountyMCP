"""Scenario-owned session boundary for node-run claims."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import NodeRunClaim, NodeRunClaimRequest
from api.infrastructure.orchestration.run_claim_transaction import claim_node_run_in_session


class RunClaimStore:
    """Durable write boundary for node-run claim/deduplication semantics."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def claim_node_run(self, request: NodeRunClaimRequest) -> NodeRunClaim:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            return await claim_node_run_in_session(session, request=request, now=now)
