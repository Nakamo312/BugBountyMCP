from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from api.domain.models import ScopeRuleModel
from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.adapters.base import \
    SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.scope_rule import \
    ScopeRuleRepository


class SQLAlchemyScopeRuleRepository(SQLAlchemyAbstractRepository, ScopeRuleRepository):
    def __init__(self, session):
        super().__init__(session)
        self.model = ScopeRuleModel
    
    async def get(self, id: UUID) -> Optional[ScopeRuleModel]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def create(self, entity: ScopeRuleModel) -> ScopeRuleModel:
        self.session.add(entity)
        await self.session.flush()
        return entity
    
    async def update(self, id: UUID, entity: ScopeRuleModel) -> ScopeRuleModel:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            raise EntityNotFound(f"Scope rule {id} not found")
        
        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)
        
        await self.session.flush()
        return existing
    
    async def find_by_program(self, program_id: UUID) -> List[ScopeRuleModel]:
        result = await self.session.execute(
            select(self.model).where(self.model.program_id == program_id)
        )
        return list(result.scalars().all())