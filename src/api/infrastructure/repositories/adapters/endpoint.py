"""Endpoint repository"""
from typing import Optional
from uuid import UUID
from sqlalchemy.dialects.postgresql import array
from api.infrastructure.repositories.adapters.sqlalchemy_repository import SQLAlchemyBaseRepository
from src.api.domain.models import EndpointModel



class SQLAlchemyEndpointRepository(SQLAlchemyBaseRepository[EndpointModel]):
    """Repository for Endpoint entities"""
    
    model = EndpointModel
    unique_fields = [("host_id", "service_id", "normalized_path")]
    
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
            **kwargs: Additional fields (title, content_length, etc.)
            
        Returns:
            Endpoint entity with method added to methods list
        """
        # Try to find existing endpoint
        existing = await self.get_by_fields(
            host_id=host_id,
            service_id=service_id,
            normalized_path=normalized_path
        )
        
        if existing:
            # Add method to list if not present
            methods = existing.methods or []
            if method not in methods:
                methods.append(method)
                
            # Update endpoint
            update_data = {"methods": methods}
            if status_code:
                update_data["status_code"] = status_code
            update_data.update(kwargs)
            
            return await self.update(existing.id, update_data)
        
        # Create new endpoint
        data = {
            "host_id": host_id,
            "service_id": service_id,
            "path": path,
            "normalized_path": normalized_path,
            "methods": [method],
            "status_code": status_code,
            **kwargs
        }
        return await self.create(data)
