from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from api.infrastructure.database.models import HeaderModel
from api.infrastructure.repositories.base_repo import BaseRepository


class HeaderRepository(BaseRepository[HeaderModel]):
    """PostgreSQL repository for HeaderModel"""

    model = HeaderModel
    unique_fields = [('endpoint_id', 'name', 'header_type')]

    async def get_by_endpoint(
        self, endpoint_id: UUID, header_type: Optional[str] = None
    ) -> List[HeaderModel]:
        """Get all headers for an endpoint, optionally filtered by type"""
        query = select(self.model).where(self.model.endpoint_id == endpoint_id)
        
        if header_type:
            query = query.where(self.model.header_type == header_type)
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_request_headers(self, endpoint_id: UUID) -> List[HeaderModel]:
        """Get request headers for an endpoint"""
        return await self.get_by_endpoint(endpoint_id, header_type='request')

    async def get_response_headers(self, endpoint_id: UUID) -> List[HeaderModel]:
        """Get response headers for an endpoint"""
        return await self.get_by_endpoint(endpoint_id, header_type='response')