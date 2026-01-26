# src/api/infrastructure/queries/host.py
from typing import Optional, List, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.models import HostModel
from api.infrastructure.queries.interfaces.base import AbstractQueryRepository
from api.infrastructure.queries.interfaces.host_query import HostQuery



class SQLAlchemyHostQuery(HostQuery):
    model = HostModel

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: UUID) -> Optional[HostModel]:
        return await self.get_by_fields(id=id)

    async def find_by_fields(self, **filters) -> Optional[HostModel]:
        from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
        repo = SQLAlchemyAbstractRepository(self.session)
        repo.model = HostModel
        return await repo.get_by_fields(**filters)

    async def list(self, filters: Optional[Dict] = None) -> List[HostModel]:
        from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
        repo = SQLAlchemyAbstractRepository(self.session)
        repo.model = HostModel
        return await repo.find_many(filters=filters or {})

    async def get_host(self, program_id: UUID, host: str) -> Optional[HostModel]:
        return await self.find_by_fields(program_id=program_id, host=host)

    async def list_hosts(self, program_id: UUID) -> List[HostModel]:
        return await self.list(filters={"program_id": program_id})
