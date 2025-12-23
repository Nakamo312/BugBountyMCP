"""Host-IP mapping repository"""
from uuid import UUID

from api.domain.models import HostIPModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository



class SQLAlchemyHostIPRepository(SQLAlchemyAbstractRepository, HostIPRepository):
    model = HostIPModel

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
