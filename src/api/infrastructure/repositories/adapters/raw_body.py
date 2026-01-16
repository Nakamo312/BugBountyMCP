"""Raw body repository adapter"""

from uuid import UUID

from api.domain.models import RawBodyModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository


class SQLAlchemyRawBodyRepository(SQLAlchemyAbstractRepository, AbstractRepository[RawBodyModel]):
    """Repository for raw HTTP request bodies"""

    model = RawBodyModel
    unique_fields = [("endpoint_id", "body_content")]

    async def ensure(
        self,
        endpoint_id: UUID,
        body_content: str,
    ) -> RawBodyModel:
        entity = RawBodyModel(
            endpoint_id=endpoint_id,
            body_content=body_content
        )

        return await self.upsert(
            entity,
            conflict_fields=["endpoint_id", "body_content"],
            update_fields=[]
        )
