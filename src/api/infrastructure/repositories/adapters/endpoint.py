from typing import Optional, List
from uuid import UUID

from sqlalchemy import and_, select

from api.domain.models import EndpointModel

from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository


class SQLAlchemyEndpointRepository(SQLAlchemyAbstractRepository, EndpointRepository):
    model = EndpointModel

    async def ensure(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        normalized_path: str,
        method: str,
        status_code: int | None,
    ) -> EndpointModel:

        entity = EndpointModel(
            host_id=host_id,
            service_id=service_id,
            path=path,
            normalized_path=normalized_path,
            methods=[method],
            status_code=status_code
        )

        endpoint = await self.upsert(
            entity,
            conflict_fields=["host_id", "path"],
            update_fields=["status_code"]
        )

        if method not in endpoint.methods:
            endpoint.methods.append(method)
            endpoint = await self.update(endpoint.id, endpoint)

        return endpoint
    
    async def find_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[EndpointModel]:
        """Find endpoints by host_id"""
        query = select(EndpointModel).where(
            EndpointModel.host_id == host_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())