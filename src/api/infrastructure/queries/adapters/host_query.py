from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional, List, Dict, Any

from api.domain.models import HostModel
from api.infrastructure.queries.interfaces.host_query import HostQuery


class SQLAlchemyHostQuery(SQLAlchemyAbstractQueryRepository, HostQuery):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: UUID) -> Optional[HostModel]:
        result = await self.session.execute(select(HostModel).where(HostModel.id == id))
        return result.scalar_one_or_none()

    async def find_by_fields(self, **filters) -> Optional[HostModel]:
        conditions = [getattr(HostModel, k) == v for k, v in filters.items() if hasattr(HostModel, k)]
        if not conditions:
            return None
        result = await self.session.execute(select(HostModel).where(and_(*conditions)))
        return result.scalar_one_or_none()

    async def list(self, filters: Optional[Dict[str, Any]] = None) -> List[HostModel]:
        query = select(HostModel)
        if filters:
            conditions = [getattr(HostModel, k) == v for k, v in filters.items() if hasattr(HostModel, k)]
            if conditions:
                query = query.where(and_(*conditions))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_host(self, program_id: UUID, host: str) -> Optional[HostModel]:
        return await self.find_by_fields(program_id=program_id, host=host)

    async def list_hosts(self, program_id: UUID) -> List[HostModel]:
        return await self.list(filters={"program_id": program_id})
