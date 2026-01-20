"""Header repository"""

from typing import List
from uuid import UUID

from sqlalchemy import select

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.header import HeaderRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository



class SQLAlchemyHeaderRepository(SQLAlchemyAbstractRepository, HeaderRepository):
    """Repository for Header entities"""

    model = HeaderModel

    async def ensure(
        self,
        endpoint_id: UUID,
        name: str,
        value: str,
    ) -> HeaderModel:
        entity = HeaderModel(
            endpoint_id=endpoint_id,
            name=name,
            value=value
        )

        return await self.upsert(
            entity,
            conflict_fields=["endpoint_id", "name"],
            update_fields=["value"]
        )
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[HeaderModel]:
        """Find headers by endpoint_id"""
        query = select(HeaderModel).where(
            HeaderModel.endpoint_id == endpoint_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())