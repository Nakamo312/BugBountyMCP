"""Service repository"""
from typing import Dict
from uuid import UUID

from api.domain.models import ServiceModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository


class SQLAlchemyServiceRepository(SQLAlchemyAbstractRepository):
    model = ServiceModel

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
