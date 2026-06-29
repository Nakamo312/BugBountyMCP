"""Agent inbox persistence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.adapters.orm import agent_inbox


@dataclass(frozen=True, slots=True)
class AgentInboxMessage:
    program_id: Any
    message_type: str
    payload: dict[str, Any]
    dedupe_key: str
    campaign_id: Any | None = None
    correlation_id: Any | None = None
    event_id: Any | None = None
    workflow_id: Any | None = None
    workflow_run_id: Any | None = None
    subscription_id: Any | None = None


class AgentInboxStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def enqueue_once(self, message: AgentInboxMessage) -> Any | None:
        statement = (
            insert(agent_inbox)
            .values(
                subscription_id=message.subscription_id,
                workflow_id=message.workflow_id,
                workflow_run_id=message.workflow_run_id,
                program_id=message.program_id,
                campaign_id=message.campaign_id,
                correlation_id=message.correlation_id,
                event_id=message.event_id,
                message_type=message.message_type,
                payload=message.payload,
                dedupe_key=message.dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(agent_inbox.c.id)
        )

        async with self.session_factory() as session:
            result = await session.execute(statement)
            inserted_id = result.scalar_one_or_none()
            if hasattr(session, "commit"):
                await session.commit()

        return inserted_id


__all__ = ["AgentInboxMessage", "AgentInboxStore"]
