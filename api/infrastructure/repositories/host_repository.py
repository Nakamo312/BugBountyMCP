"""Host repository implementation with deduplication"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from ...domain.repositories import HostRepository
from ..database.models import HostModel
from ..normalization import Deduplicator


class PostgresHostRepository(HostRepository):
    """PostgreSQL implementation of Host repository"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, host_data: dict) -> dict:
        """Save or update host"""
        existing = await self.find_by_host(host_data['host'])
        
        if existing:
            # Update existing
            result = await self.session.execute(
                select(HostModel).where(
                    HostModel.program_id == host_data['program_id'],
                    HostModel.host == host_data['host']
                )
            )
            model = result.scalar_one()
            model.in_scope = host_data.get('in_scope', model.in_scope)
        else:
            # Create new
            model = HostModel(
                id=host_data.get('id'),
                program_id=host_data['program_id'],
                host=host_data['host'],
                in_scope=host_data.get('in_scope', True)
            )
            self.session.add(model)
        
        await self.session.flush()
        return self._to_dict(model)
    
    async def get_by_id(self, id: UUID) -> Optional[dict]:
        """Get host by ID"""
        result = await self.session.execute(
            select(HostModel).where(HostModel.id == id)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def delete(self, id: UUID) -> None:
        """Delete host"""
        result = await self.session.execute(
            select(HostModel).where(HostModel.id == id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
    
    async def get_by_program(self, program_id: UUID) -> List[dict]:
        """Get all hosts for program"""
        result = await self.session.execute(
            select(HostModel).where(HostModel.program_id == program_id)
        )
        models = result.scalars().all()
        return [self._to_dict(m) for m in models]
    
    async def find_by_host(self, host: str) -> Optional[dict]:
        """Find host by hostname"""
        result = await self.session.execute(
            select(HostModel).where(HostModel.host == host)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def bulk_upsert(self, hosts_data: List[dict]) -> None:
        """
        Bulk insert/update hosts with deduplication
        Uses PostgreSQL INSERT ... ON CONFLICT
        """
        if not hosts_data:
            return
        
        # Deduplicate input
        unique_hosts = Deduplicator.deduplicate_by_key(
            hosts_data,
            lambda h: (h['program_id'], h['host'].lower())
        )
        
        # Prepare data for upsert
        values = [
            {
                'id': h.get('id'),
                'program_id': h['program_id'],
                'host': h['host'],
                'in_scope': h.get('in_scope', True)
            }
            for h in unique_hosts
        ]
        
        # PostgreSQL upsert
        stmt = insert(HostModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=['program_id', 'host'],
            set_={
                'in_scope': stmt.excluded.in_scope
            }
        )
        
        await self.session.execute(stmt)
        await self.session.flush()
    
    @staticmethod
    def _to_dict(model: HostModel) -> dict:
        """Convert ORM model to dict"""
        return {
            'id': model.id,
            'program_id': model.program_id,
            'host': model.host,
            'in_scope': model.in_scope
        }
