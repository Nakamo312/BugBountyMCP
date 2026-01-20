"""Input parameter repository"""
from typing import List
from uuid import UUID

from sqlalchemy import select

from api.domain.models import InputParameterModel
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.input_parameters import InputParameterRepository



class SQLAlchemyInputParameterRepository(SQLAlchemyAbstractRepository, InputParameterRepository):
    model = InputParameterModel

    async def ensure(
        self,
        endpoint_id: UUID,
        service_id: UUID,
        name: str,
        location: str,
        example_value: str | None,
    ) -> InputParameterModel:

        entity = InputParameterModel(
            endpoint_id=endpoint_id,
            service_id=service_id,
            name=name,
            location=location,
            example_value=example_value
        )

        return await self.upsert(
            entity,
            conflict_fields=["endpoint_id", "location", "name"],
            update_fields=["example_value"]
        )
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[InputParameterModel]:
        """Find input parameters by endpoint_id"""
        query = select(InputParameterModel).where(
            InputParameterModel.endpoint_id == endpoint_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

