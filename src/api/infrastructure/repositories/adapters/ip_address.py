"""IP Address repository"""
from uuid import UUID
from api.domain.models import IPAddressModel, ProgramModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.ip_address import IPAddressRepository


class SQLAlchemyIPAddressRepository(SQLAlchemyAbstractRepository, IPAddressRepository):
    model = IPAddressModel

    async def ensure(
        self,
        program_id: UUID,
        address: str,
        in_scope: bool = True,
    ) -> IPAddressModel:

        entity = IPAddressModel(
            program_id=program_id,
            address=address,
            in_scope=in_scope
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "address"],
            update_fields=["in_scope"]
        )
