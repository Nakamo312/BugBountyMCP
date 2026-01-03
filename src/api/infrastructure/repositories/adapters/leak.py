from typing import List
from uuid import UUID

from api.domain.models import LeakModel
from api.infrastructure.repositories.interfaces.leak import LeakRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository


class SQLAlchemyLeakRepository(SQLAlchemyAbstractRepository, LeakRepository):
    model = LeakModel

    async def find_by_program(self, program_id: UUID) -> List[LeakModel]:
        return await self.find_many(filters={"program_id": program_id})

    async def ensure(
        self,
        program_id: UUID,
        content: str,
        endpoint_id: UUID | None = None,
    ) -> LeakModel:
        entity = LeakModel(
            program_id=program_id,
            content=content,
            endpoint_id=endpoint_id,
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "content", "endpoint_id"],
        )
