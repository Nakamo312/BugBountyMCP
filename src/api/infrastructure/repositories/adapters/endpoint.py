from typing import Optional, List
from uuid import UUID

from sqlalchemy import and_, select

from api.domain.models import EndpointModel

from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository


class SQLAlchemyEndpointRepository(SQLAlchemyAbstractRepository, EndpointRepository):
    """Repository for Endpoint entities"""
    
    def __init__(self, session):
        super().__init__(session)
        self.model = EndpointModel
        self.unique_fields = [("host_id", "service_id", "normalized_path")]
    
    async def get(self, id: UUID) -> Optional[EndpointModel]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_fields(self, **filters) -> Optional[EndpointModel]:
        conditions = [
            getattr(self.model, key) == value 
            for key, value in filters.items()
            if hasattr(self.model, key)
        ]
        if not conditions:
            return None
            
        result = await self.session.execute(
            select(self.model).where(and_(*conditions))
        )
        return result.scalar_one_or_none()
    
    async def create(self, entity: EndpointModel) -> EndpointModel:
        self.session.add(entity)
        await self.session.flush()
        return entity
    
    async def update(self, id: UUID, entity: EndpointModel) -> EndpointModel:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            raise EntityNotFound(f"Endpoint {id} not found")
        
        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)
        
        await self.session.flush()
        return existing
    
    async def delete(self, id: UUID) -> None:
        endpoint = await self.get(id)
        if endpoint:
            await self.session.delete(endpoint)
            await self.session.flush()
    
    async def upsert_with_method(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        method: str,
        normalized_path: str,
        status_code: Optional[int] = None,
        **kwargs
    ) -> EndpointModel:
        """
        Upsert endpoint and add HTTP method to methods list.
        
        Args:
            host_id: Host entity ID
            service_id: Service entity ID
            path: Original URL path
            method: HTTP method (GET, POST, etc.)
            normalized_path: Normalized/lowercased path
            status_code: HTTP status code
            **kwargs: Additional fields
            
        Returns:
            Endpoint entity with method added to methods list
        """
        from sqlalchemy import select
        
        existing = await self.get_by_fields(
            host_id=host_id,
            service_id=service_id,
            normalized_path=normalized_path
        )
        
        if existing:
            methods = existing.methods or []
            if method not in methods:
                methods.append(method)
                
            update_data = {"methods": methods}
            if status_code:
                update_data["status_code"] = status_code
            
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    update_data[key] = value
            
            updated_endpoint = existing.copy(update=update_data)
            return await self.update(existing.id, updated_endpoint)
        
        data = {
            "host_id": host_id,
            "service_id": service_id,
            "path": path,
            "normalized_path": normalized_path,
            "methods": [method],
            "status_code": status_code,
        }
        data.update(kwargs)
        
        endpoint = EndpointModel(**data)
        return await self.create(endpoint)
    
    async def find_by_host(self, host_id: UUID) -> List[EndpointModel]:
        """Find all endpoints for a host"""
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(self.model).where(self.model.host_id == host_id)
        )
        return list(result.scalars().all())
    
    async def find_by_service(self, service_id: UUID) -> List[EndpointModel]:
        """Find all endpoints for a service"""
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(self.model).where(self.model.service_id == service_id)
        )
        return list(result.scalars().all())