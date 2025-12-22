"""Base repository with full CRUD and pagination support"""
from typing import TypeVar, Optional, List, Tuple, Dict, Any
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.repositories.interfaces.repository import AbstractRepository
from src.api.domain.models import AbstractModel
from api.infrastructure.database.repositories import SQLAlchemyAbstractRepository

Model = TypeVar('T', bound=AbstractModel)


class UniqueConstraintViolation(Exception):
    """Raised when unique constraint is violated"""
    def __init__(self, fields: List[str], values: Dict[str, Any]):
        self.fields = fields
        self.values = values
        super().__init__(f"Unique constraint violated for {fields}: {values}")


class SQLAlchemyBaseRepository(SQLAlchemyAbstractRepository, AbstractRepository[Model]):
    """
    Base repository implementing common CRUD operations.
    
    Subclasses should define:
    - model: SQLAlchemy model class
    - unique_fields: List of tuples defining unique constraints
    """
    model: type[Model]
    unique_fields: Optional[List[Tuple[str, ...]]] = None

    async def get(self, id: UUID) -> Optional[Model]:
        """Get entity by ID"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_fields(self, **filters) -> Optional[Model]:
        """
        Get entity by arbitrary fields.
        
        Example:
            repo.get_by_fields(program_id=uuid, host="example.com")
        """
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
    ) -> List[Model]:
        """
        Find multiple entities with pagination and filtering.
        
        Args:
            filters: Dict of field:value pairs to filter by
            limit: Maximum number of results (default 100)
            offset: Number of results to skip (default 0)
            order_by: Field name to order by (prefix with - for DESC)
            
        Example:
            repo.find_many(
                filters={"program_id": uuid, "in_scope": True},
                limit=50,
                offset=0,
                order_by="-created_at"
            )
        """
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
        """
        Count entities matching filters.
        
        Args:
            filters: Dict of field:value pairs to filter by
            
        Returns:
            Number of matching entities
        """
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

    async def create(self, data: Dict[str, Any]) -> Model:
        """
        Create new entity.
        
        Args:
            data: Entity data as dict
            
        Returns:
            Created entity
            
        Raises:
            UniqueConstraintViolation: If unique constraint violated
        """
        model = self.model(**data)
        self.session.add(model)
        
        try:
            await self.session.flush()
            return model
        except IntegrityError as e:
            await self.session.rollback()
            raise UniqueConstraintViolation(
                fields=self.unique_fields[0] if self.unique_fields else [],
                values=data
            ) from e

    async def update(self, id: UUID, data: Dict[str, Any]) -> Model:
        """
        Update entity by ID.
        
        Args:
            id: Entity ID
            data: Fields to update
            
        Returns:
            Updated entity
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        model = result.scalar_one()
        
        for key, value in data.items():
            if hasattr(model, key):
                setattr(model, key, value)
        
        await self.session.flush()
        return model

    async def delete(self, id: UUID) -> None:
        """Delete entity by ID"""
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()

    async def get_or_create(
        self, 
        defaults: Optional[Dict[str, Any]] = None,
        **filters
    ) -> Tuple[Model, bool]:
        """
        Get existing entity or create new one.
        
        Args:
            defaults: Additional fields for creation
            **filters: Fields to search by
            
        Returns:
            Tuple of (entity, created) where created is True if new
        """
        existing = await self.get_by_fields(**filters)
        if existing:
            return existing, False
        
        data = {**filters, **(defaults or {})}
        model = await self.create(data)
        return model, True

    async def upsert(
        self,
        data: Dict[str, Any],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> Model:
        """
        Insert or update using PostgreSQL ON CONFLICT.
        
        Args:
            data: Entity data
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict (all except conflict_fields if None)
            
        Returns:
            Created or updated entity
        """
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

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[Model]:
        """
        Create multiple entities.
        
        Args:
            items: List of entity data dicts
            
        Returns:
            List of created entities
        """
        if not items:
            return []
        
        models = [self.model(**item) for item in items]
        self.session.add_all(models)
        await self.session.flush()
        return models

    async def bulk_upsert(
        self,
        items: List[Dict[str, Any]],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        """
        Bulk insert or update.
        
        Args:
            items: List of entity data dicts
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict
        """
        if not items:
            return
        
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
