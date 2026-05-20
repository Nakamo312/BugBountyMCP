"""Persistence for raw artifact metadata."""
from __future__ import annotations

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.adapters.orm import raw_artifacts


class RawArtifactRepository:
    """Write metadata rows for externally stored raw artifacts."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def record(self, metadata: dict[str, Any]) -> None:
        async with self.session_factory() as session:
            await session.execute(insert(raw_artifacts).values(**metadata))
            await session.commit()
