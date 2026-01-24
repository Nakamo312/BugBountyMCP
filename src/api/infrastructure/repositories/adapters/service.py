"""Service repository"""
from typing import Dict, List
from uuid import UUID

from sqlalchemy import select

from api.domain.models import ServiceModel, IPAddressModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository


class SQLAlchemyServiceRepository(SQLAlchemyAbstractRepository, ServiceRepository):
    model = ServiceModel

    async def find_by_program_id(self, program_id: UUID) -> List[ServiceModel]:
        """Find all services for a program via ip_addresses join"""
        query = (
            select(ServiceModel)
            .join(IPAddressModel, ServiceModel.ip_id == IPAddressModel.id)
            .where(IPAddressModel.program_id == program_id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def ensure(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: dict,
        favicon_hash: str | None = None,
        websocket: bool = False,
    ) -> ServiceModel:

        entity = ServiceModel(
            ip_id=ip_id,
            scheme=scheme,
            port=port,
            technologies=technologies,
            favicon_hash=favicon_hash,
            websocket=websocket
        )

        service = await self.upsert(
            entity,
            conflict_fields=["ip_id", "port"],
            update_fields=["technologies", "favicon_hash", "websocket"]
        )

        if technologies:
            merged = {**service.technologies, **technologies}
            if merged != service.technologies:
                service = await self.update(
                    service.id,
                    service.copy(update={"technologies": merged})
                )

        return service
