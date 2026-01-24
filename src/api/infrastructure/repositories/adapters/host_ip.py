"""Host-IP mapping repository"""
from typing import List
from uuid import UUID

from sqlalchemy import select

from api.domain.models import HostIPModel, HostModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository


class SQLAlchemyHostIPRepository(SQLAlchemyAbstractRepository, HostIPRepository):
    model = HostIPModel

    async def find_by_program_id(self, program_id: UUID) -> List[HostIPModel]:
        """Find all host-IP mappings for a program via hosts join"""
        query = (
            select(HostIPModel)
            .join(HostModel, HostIPModel.host_id == HostModel.id)
            .where(HostModel.program_id == program_id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def ensure(
        self,
        host_id: UUID,
        ip_id: UUID,
        source: str,
    ) -> HostIPModel:

        entity = HostIPModel(
            host_id=host_id,
            ip_id=ip_id,
            source=source
        )

        return await self.upsert(
            entity,
            conflict_fields=["host_id", "ip_id"],
            update_fields=["source"]
        )
