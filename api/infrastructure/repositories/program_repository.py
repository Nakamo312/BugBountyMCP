"""Program repository implementation"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories import ProgramRepository
from ..database.models import ProgramModel


class PostgresProgramRepository(ProgramRepository):
    """PostgreSQL implementation of Program repository"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save(self, program_data: dict) -> dict:
        """Save or update program"""
        existing = await self.get_by_id(program_data.get('id'))
        
        if existing:
            # Update
            result = await self.session.execute(
                select(ProgramModel).where(ProgramModel.id == program_data['id'])
            )
            model = result.scalar_one()
            model.name = program_data.get('name', model.name)
        else:
            # Create
            model = ProgramModel(
                id=program_data.get('id'),
                name=program_data['name']
            )
            self.session.add(model)
        
        await self.session.flush()
        return self._to_dict(model)
    
    async def get_by_id(self, id: UUID) -> Optional[dict]:
        """Get program by ID"""
        result = await self.session.execute(
            select(ProgramModel).where(ProgramModel.id == id)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def delete(self, id: UUID) -> None:
        """Delete program"""
        result = await self.session.execute(
            select(ProgramModel).where(ProgramModel.id == id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self.session.delete(model)
            await self.session.flush()
    
    async def get_by_name(self, name: str) -> Optional[dict]:
        """Find program by name"""
        result = await self.session.execute(
            select(ProgramModel).where(ProgramModel.name == name)
        )
        model = result.scalar_one_or_none()
        return self._to_dict(model) if model else None
    
    async def list_all(self) -> List[dict]:
        """List all programs"""
        result = await self.session.execute(select(ProgramModel))
        models = result.scalars().all()
        return [self._to_dict(m) for m in models]
    
    @staticmethod
    def _to_dict(model: ProgramModel) -> dict:
        """Convert ORM model to dict"""
        return {
            'id': model.id,
            'name': model.name
        }
