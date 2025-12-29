"""Header repository"""

from uuid import UUID

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository



class SQLAlchemyHeaderRepository(SQLAlchemyAbstractRepository, AbstractRepository[HeaderModel]):
    """Repository for Header entities"""

    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]

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
