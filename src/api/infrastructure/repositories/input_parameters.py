from typing import List, Optional
from uuid import UUID
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import InputParameterModel
from .base_repo import BaseRepository


class InputParameterRepository(BaseRepository[InputParameterModel]):
    """PostgreSQL repository for InputParameterModel"""

    model = InputParameterModel
    unique_fields = [('endpoint_id', 'location', 'name')]

    async def get_by_endpoint(self, endpoint_id: UUID) -> List[InputParameterModel]:
        """Get all parameters for an endpoint"""
        result = await self.session.execute(
            select(self.model).where(self.model.endpoint_id == endpoint_id)
        )
        return result.scalars().all()

    async def get_by_location(
        self, endpoint_id: UUID, location: str
    ) -> List[InputParameterModel]:
        """Get all parameters for an endpoint by location"""
        result = await self.session.execute(
            select(self.model).where(
                self.model.endpoint_id == endpoint_id,
                self.model.location == location
            )
        )
        return result.scalars().all()