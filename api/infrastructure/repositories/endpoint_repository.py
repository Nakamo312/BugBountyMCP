"""Endpoint repository implementation with path normalization"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from ...domain.repositories import EndpointRepository
from ..database.models import EndpointModel
from ..normalization import PathNormalizer, Deduplicator


class PostgresEndpointRepository(EndpointRepository):
    """PostgreSQL implementation of Endpoint repository"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, endpoint_data: dict) -> dict:
        """Save or update endpoint"""
        # Normalize path if not provided
        if not endpoint_data.get('normalized_path'):
            full_url = f"http://dummy{endpoint_data['path']}"
            endpoint_data['normalized_path'] = PathNormalizer.normalize_path(full_url)
        
        existing = await self.find_by_normalized_path(
            endpoint_data['service_id'],
            endpoint_data['normalized_path'],
            endpoint_data['method']
        )
        
        if existing:
            # Update existing
            result = await self.session.execute(
                select(EndpointModel).where(EndpointModel.id == existing['id'])
            )
            model = result.scalar_one()
            model.path = endpoint_data.get('path', model.path)
            model.status_code = endpoint_data.get('status_code', model.status_code)
        else:
            # Create new
            model = EndpointModel(
                id=endpoint_data.get('id'),
                service_id=endpoint_data['service_id'],
                host_id=endpoint_data['host_id'],
                path=endpoint_data['path'],
                method=endpoint_data['method'],
                status_code=endpoint_data.get('status_code', 200),
                normalized_path=endpoint_data['normalized_path']
            )
            self.session.add(model)
        
        await self.session.flush()
        return self._to_dict(model)
    
    async def get_by_id(self, id: UUID) -> Optional[dict]:
        """Get endpoint by ID"""
        result = await self.session.execute(
            select(EndpointModel).where(EndpointModel.id == id)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def delete(self, id: UUID) -> None:
        """Delete endpoint"""
        result = await self.session.execute(
            select(EndpointModel).where(EndpointModel.id == id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
    
    async def get_by_service(self, service_id: UUID) -> List[dict]:
        """Get all endpoints for service"""
        result = await self.session.execute(
            select(EndpointModel).where(EndpointModel.service_id == service_id)
        )
        models = result.scalars().all()
        return [self._to_dict(m) for m in models]
    
    async def get_by_host(self, host_id: UUID) -> List[dict]:
        """Get all endpoints for host"""
        result = await self.session.execute(
            select(EndpointModel).where(EndpointModel.host_id == host_id)
        )
        models = result.scalars().all()
        return [self._to_dict(m) for m in models]
    
    async def find_by_normalized_path(
        self, service_id: UUID, normalized_path: str, method: str
    ) -> Optional[dict]:
        """Find endpoint by normalized path"""
        result = await self.session.execute(
            select(EndpointModel).where(
                EndpointModel.service_id == service_id,
                EndpointModel.normalized_path == normalized_path,
                EndpointModel.method == method
            )
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def bulk_upsert(self, endpoints_data: List[dict]) -> None:
        """
        Bulk insert/update endpoints with deduplication by normalized path
        """
        if not endpoints_data:
            return
        
        # Normalize paths
        for endpoint in endpoints_data:
            if not endpoint.get('normalized_path'):
                full_url = f"http://dummy{endpoint['path']}"
                endpoint['normalized_path'] = PathNormalizer.normalize_path(full_url)
        
        # Deduplicate by (service_id, normalized_path, method)
        unique_endpoints = Deduplicator.deduplicate_by_key(
            endpoints_data,
            lambda e: (e['service_id'], e['normalized_path'], e['method'])
        )
        
        # Prepare data
        values = [
            {
                'id': e.get('id'),
                'service_id': e['service_id'],
                'host_id': e['host_id'],
                'path': e['path'],
                'method': e['method'],
                'status_code': e.get('status_code', 200),
                'normalized_path': e['normalized_path']
            }
            for e in unique_endpoints
        ]
        
        # PostgreSQL upsert
        stmt = insert(EndpointModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=['service_id', 'normalized_path', 'method'],
            set_={
                'path': stmt.excluded.path,
                'status_code': stmt.excluded.status_code
            }
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
    
    @staticmethod
    def _to_dict(model: EndpointModel) -> dict:
        """Convert ORM model to dict"""
        return {
            'id': model.id,
            'service_id': model.service_id,
            'host_id': model.host_id,
            'path': model.path,
            'method': model.method,
            'status_code': model.status_code,
            'normalized_path': model.normalized_path
        }
