"""SQLAlchemy research signal repository."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.infrastructure.adapters.orm import research_signals
from api.infrastructure.repositories.interfaces.research_signal import ResearchSignalRepository


class SQLAlchemyResearchSignalRepository(ResearchSignalRepository):
    """PostgreSQL-backed research signal repository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_signal(
        self,
        *,
        program_id: UUID,
        signal_type: str,
        signal_version: str,
        rule_id: str,
        rule_version: str,
        evidence_fingerprint: str,
        confidence: float,
        payload_json: dict[str, Any],
        asset_type: str | None = None,
        asset_id: str | None = None,
        observation_id: UUID | None = None,
        producer_run_id: UUID | None = None,
    ) -> None:
        statement = insert(research_signals).values(
            program_id=program_id,
            producer_run_id=producer_run_id,
            signal_type=signal_type,
            signal_version=signal_version,
            rule_id=rule_id,
            rule_version=rule_version,
            asset_type=asset_type,
            asset_id=asset_id,
            observation_id=observation_id,
            evidence_fingerprint=evidence_fingerprint,
            confidence=max(0.0, min(float(confidence), 1.0)),
            payload_json=payload_json,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_research_signal_fingerprint",
            set_={
                "producer_run_id": producer_run_id,
                "asset_type": asset_type,
                "asset_id": asset_id,
                "observation_id": observation_id,
                "confidence": max(0.0, min(float(confidence), 1.0)),
                "payload_json": payload_json,
            },
        )
        await self.session.execute(statement)
