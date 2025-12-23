"""Input parameter repository"""
from uuid import UUID
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

