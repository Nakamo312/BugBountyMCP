from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from ..database.models import HostModel
from .base_repo import BaseRepository
from ..normalization import Deduplicator


class HostRepository(BaseRepository[HostModel]):
    """PostgreSQL implementation of Host repository"""

    model = HostModel
    unique_fields = [('program_id', 'host')]

    async def find_by_host(self, program_id: UUID, host: str) -> Optional[HostModel]:
        """Find host by program and hostname"""
        return await self.get_by_unique_fields(program_id=program_id, host=host)

    async def get_by_program(self, program_id: UUID) -> List[HostModel]:
        """Get all hosts for program"""
        result = await self.session.execute(
            select(self.model).where(self.model.program_id == program_id)
        )
        return result.scalars().all()
