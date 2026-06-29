"""Research signal repository interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class ResearchSignalRepository(ABC):
    """Repository interface for durable research signals."""

    @abstractmethod
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
        """Insert or update a signal identified by its program/type/version/fingerprint."""
        raise NotImplementedError
