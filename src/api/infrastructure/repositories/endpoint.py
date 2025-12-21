from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.repositories.base_repo import BaseRepository

from ..database.models import EndpointModel
from ..normalization import PathNormalizer, Deduplicator



class EndpointRepository(BaseRepository[EndpointModel]):
    """PostgreSQL implementation of Endpoint repository"""

    model = EndpointModel
    unique_fields = [('host_id', 'path')]

    async def find_by_path(
        self, host_id: UUID, path: str
    ) -> Optional[EndpointModel]:
        """Find endpoint by host and path"""
        return await self.get_by_unique_fields(host_id=host_id, path=path)

    async def add_method(
        self, endpoint_id: UUID, method: str
    ) -> EndpointModel:
        """Add method to endpoint if not already present"""
        endpoint = await self.get_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint {endpoint_id} not found")
        
        methods = endpoint.methods or []
        if method not in methods:
            endpoint.methods = methods + [method]
            await self.session.flush()
        
        return endpoint

    async def upsert_with_method(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        method: str,
        normalized_path: str,
        status_code: int = 200
    ) -> EndpointModel:
        """
        Upsert endpoint and add method to methods array if not present.
        Pure ORM approach - works with any database.
        """
        # Try to find existing endpoint
        existing = await self.find_by_path(host_id=host_id, path=path)

        if existing:
            # Update basic fields if changed
            if existing.path != path:
                existing.path = path
            if existing.status_code != status_code:
                existing.status_code = status_code

            # Add method if not present
            if method not in (existing.methods or []):
                if existing.methods is None:
                    existing.methods = [method]
                else:
                    existing.methods.append(method)

            await self.session.flush()
            return existing

        # Create new endpoint
        return await self.create({
            'host_id': host_id,
            'service_id': service_id,
            'path': path,
            'normalized_path': normalized_path,
            'methods': [method],
            'status_code': status_code
        })

    async def get_by_service(self, service_id: UUID) -> List[EndpointModel]:
        """Get all endpoints for a service"""
        result = await self.session.execute(
            select(self.model).where(self.model.service_id == service_id)
        )
        return result.scalars().all()

    async def get_by_host(self, host_id: UUID) -> List[EndpointModel]:
        """Get all endpoints for a host"""
        result = await self.session.execute(
            select(self.model).where(self.model.host_id == host_id)
        )
        return result.scalars().all()