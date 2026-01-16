from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select

from api.domain.models import RootInputModel
from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.adapters.base import \
    SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.root_input import \
    RootInputRepository


class SQLAlchemyRootInputRepository(SQLAlchemyAbstractRepository, RootInputRepository):
    def __init__(self, session):
        super().__init__(session)
        self.model = RootInputModel
    
    async def get(self, id: UUID) -> Optional[RootInputModel]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def create(self, entity: RootInputModel) -> RootInputModel:
        self.session.add(entity)
        await self.session.flush()
        return entity
    
    async def update(self, id: UUID, entity: RootInputModel) -> RootInputModel:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            raise EntityNotFound(f"Root input {id} not found")
        
        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)
        
        await self.session.flush()
        return existing
    
    async def find_by_program(self, program_id: UUID) -> List[RootInputModel]:
        result = await self.session.execute(
            select(self.model).where(self.model.program_id == program_id)
        )
        return list(result.scalars().all())

    async def delete_by_program(self, program_id: UUID) -> None:
        await self.session.execute(
            delete(self.model).where(self.model.program_id == program_id)
        )
        await self.session.flush()