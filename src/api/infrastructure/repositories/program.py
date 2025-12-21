from typing import Optional
from api.infrastructure.database.models import ProgramModel
from api.infrastructure.repositories.base_repo import BaseRepository


class ProgramRepository(BaseRepository[ProgramModel]):
    """PostgreSQL implementation of Program repository"""

    model = ProgramModel
    unique_fields = [('name',)]

    async def get_by_name(self, name: str) -> Optional[ProgramModel]:
        """Find program by name"""
        return await self.get_by_unique_fields(name=name)
