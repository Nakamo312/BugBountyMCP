from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from api.domain.models import ProgramModel
from api.infrastructure.repositories.adapters.base import \
    SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.program import \
    ProgramRepository


class UniqueConstraintViolation(Exception):
    """Raised when unique constraint is violated"""
    def __init__(self, message: str):
        super().__init__(message)


class EntityNotFound(Exception):
    """Raised when entity is not found"""
    pass


class SQLAlchemyProgramRepository(SQLAlchemyAbstractRepository, ProgramRepository):
    """Repository for Program entities"""
    
    def __init__(self, session):
        super().__init__(session)
        self.model = ProgramModel
        self.unique_fields = [("name",)]
    
    async def get(self, id: UUID) -> Optional[ProgramModel]:
        """Get program by ID"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_fields(self, **filters) -> Optional[ProgramModel]:
        """Get program by arbitrary fields"""
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
    
    async def find_many(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None
    ) -> List[ProgramModel]:
        """Find multiple programs with pagination"""
        query = select(self.model)
        
        if filters:
            conditions = [
                getattr(self.model, key) == value
                for key, value in filters.items()
                if hasattr(self.model, key)
            ]
            if conditions:
                query = query.where(and_(*conditions))
        
        if order_by:
            if order_by.startswith('-'):
                field = order_by[1:]
                if hasattr(self.model, field):
                    query = query.order_by(getattr(self.model, field).desc())
            else:
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))
        
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count programs matching filters"""
        query = select(func.count(self.model.id))
        
        if filters:
            conditions = [
                getattr(self.model, key) == value
                for key, value in filters.items()
                if hasattr(self.model, key)
            ]
            if conditions:
                query = query.where(and_(*conditions))
        
        result = await self.session.execute(query)
        return result.scalar_one()
    
    async def create(self, entity: ProgramModel) -> ProgramModel:
        """
        Create new program.
        
        Args:
            entity: ProgramModel to create
            
        Returns:
            Created ProgramModel
            
        Raises:
            UniqueConstraintViolation: If unique constraint violated
        """
        self.session.add(entity)
        
        try:
            await self.session.flush()
            return entity
        except IntegrityError as e:
            await self.session.rollback()
            raise UniqueConstraintViolation(f"Program with name '{entity.name}' already exists") from e
    
    async def update(self, id: UUID, entity: ProgramModel) -> ProgramModel:
        """
        Update existing program.
        
        Args:
            id: Program ID
            entity: Updated ProgramModel
            
        Returns:
            Updated ProgramModel
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            raise EntityNotFound(f"Program with id {id} not found")
        
        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)
        
        if hasattr(existing, 'updated_at'):
            existing.updated_at = datetime.utcnow()
        
        await self.session.flush()
        return existing
      
    async def delete(self, id: UUID) -> None:
        """Delete program by ID"""
        program = await self.get(id)
        if program:
            await self.session.delete(program)
            await self.session.flush()
    
    async def get_or_create(
        self,
        entity: ProgramModel,
        **filters
    ) -> Tuple[ProgramModel, bool]:
        """
        Get existing program or create new one.
        
        Args:
            entity: ProgramModel to create if not exists
            **filters: Fields to search by
            
        Returns:
            Tuple of (program, created) where created is True if new
        """
        existing = await self.get_by_fields(**filters)
        if existing:
            return existing, False
        
        created = await self.create(entity)
        return created, True
    
    async def upsert(
        self,
        entity: ProgramModel,
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> ProgramModel:
        """
        Insert or update program using PostgreSQL ON CONFLICT.
        
        Args:
            entity: ProgramModel to upsert
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict (all except conflict_fields if None)
            
        Returns:
            Created or updated ProgramModel
        """
        data = entity.model_dump() if hasattr(entity, 'model_dump') else entity.dict()
        
        stmt = insert(self.model).values(**data)
        
        if update_fields is None:
            update_fields = [
                key for key in data.keys() 
                if key not in conflict_fields and key != 'id'
            ]
        
        if update_fields:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_fields,
                set_={field: getattr(stmt.excluded, field) for field in update_fields}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_fields)
        
        result = await self.session.execute(stmt.returning(self.model))
        await self.session.flush()
        return result.scalar_one()
    
    async def bulk_create(self, entities: List[ProgramModel]) -> List[ProgramModel]:
        """
        Create multiple programs.
        
        Args:
            entities: List of ProgramModels to create
            
        Returns:
            List of created ProgramModels
        """
        if not entities:
            return []
        
        self.session.add_all(entities)
        await self.session.flush()
        return entities
    
    async def bulk_upsert(
        self,
        entities: List[ProgramModel],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        """
        Bulk insert or update programs.
        
        Args:
            entities: List of ProgramModels to upsert
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict
        """
        if not entities:
            return
        
        items = [
            entity.model_dump() if hasattr(entity, 'model_dump') else entity.dict()
            for entity in entities
        ]
        
        stmt = insert(self.model).values(items)
        
        if update_fields is None:
            update_fields = [
                key for key in items[0].keys() 
                if key not in conflict_fields and key != 'id'
            ]
        
        if update_fields:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_fields,
                set_={field: getattr(stmt.excluded, field) for field in update_fields}
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_fields)
        
        await self.session.execute(stmt)
        await self.session.flush()