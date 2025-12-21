"""Base repository with unique constraint handling"""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Tuple, Dict, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert

Model = TypeVar("Model")


class UniqueConstraintViolation(Exception):
    """Raised when unique constraint is violated"""
    def __init__(self, fields: List[str], values: Dict[str, Any]):
        self.fields = fields
        self.values = values
        super().__init__(f"Unique constraint violated for {fields}: {values}")


class BaseRepository(ABC, Generic[Model]):
    model: type[Model]
    
    # Subclasses должны определить unique_fields как список кортежей полей
    unique_fields: Optional[List[Tuple[str, ...]]] = None

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[Model]:
        """Get entity by ID"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_unique_fields(self, **filters) -> Optional[Model]:
        """Get entity by unique fields combination"""
        conditions = [
            getattr(self.model, key) == value 
            for key, value in filters.items()
        ]
        result = await self.session.execute(
            select(self.model).where(*conditions)
        )
        return result.scalar_one_or_none()

    async def exists_by_unique_fields(self, **filters) -> bool:
        """Check if entity exists by unique fields"""
        return await self.get_by_unique_fields(**filters) is not None

    async def create(self, data: dict, *, ignore_conflicts: bool = False) -> Model:
        """
        Create new entity.
        
        Args:
            data: Entity data
            ignore_conflicts: If True, return existing entity on conflict
        """
        model = self.model(**data)
        self.session.add(model)
        
        try:
            await self.session.flush()
            return model
        except IntegrityError:
            await self.session.rollback()
            
            if ignore_conflicts and self.unique_fields:
                # Try to find existing entity
                for unique_combo in self.unique_fields:
                    filters = {
                        field: data.get(field) 
                        for field in unique_combo 
                        if field in data
                    }
                    if len(filters) == len(unique_combo):
                        existing = await self.get_by_unique_fields(**filters)
                        if existing:
                            return existing
            
            raise UniqueConstraintViolation(
                fields=self.unique_fields[0] if self.unique_fields else [],
                values=data
            )

    async def get_or_create(
        self, 
        defaults: Optional[dict] = None,
        **filters
    ) -> Tuple[Model, bool]:
        """
        Get existing entity or create new one.
        
        Returns:
            Tuple of (entity, created) where created is True if entity was created
        """
        existing = await self.get_by_unique_fields(**filters)
        if existing:
            return existing, False
        
        data = {**filters, **(defaults or {})}
        model = await self.create(data)
        return model, True

    async def update_or_create(
        self,
        filters: dict,
        defaults: dict
    ) -> Tuple[Model, bool]:
        """
        Update existing entity or create new one.
        
        Returns:
            Tuple of (entity, created) where created is True if entity was created
        """
        existing = await self.get_by_unique_fields(**filters)
        if existing:
            for key, value in defaults.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing, False
        
        data = {**filters, **defaults}
        model = await self.create(data)
        return model, True

    async def upsert(
        self,
        data: dict,
        *,
        conflict_fields: Optional[List[str]] = None,
        update_fields: Optional[List[str]] = None
    ) -> Model:
        """
        Insert or update using PostgreSQL ON CONFLICT.
        
        Args:
            data: Entity data
            conflict_fields: Fields to check for conflicts (uses unique_fields if None)
            update_fields: Fields to update on conflict (all except conflict_fields if None)
        """
        if conflict_fields is None:
            if not self.unique_fields:
                raise ValueError("Either conflict_fields or unique_fields must be defined")
            conflict_fields = list(self.unique_fields[0])
        
        stmt = insert(self.model).values(**data)
        
        if update_fields is None:
            # Update all fields except conflict fields
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

    async def bulk_upsert(
        self,
        items: List[dict],
        *,
        conflict_fields: Optional[List[str]] = None,
        update_fields: Optional[List[str]] = None
    ) -> None:
        """Bulk insert or update"""
        if not items:
            return
        
        if conflict_fields is None:
            if not self.unique_fields:
                raise ValueError("Either conflict_fields or unique_fields must be defined")
            conflict_fields = list(self.unique_fields[0])
        
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

    async def delete(self, id: UUID) -> None:
        """Delete entity by ID"""
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()

    async def list_all(self) -> List[Model]:
        """List all entities"""
        result = await self.session.execute(select(self.model))
        return result.scalars().all()

    async def update(self, id: UUID, data: dict) -> Model:
        """Update entity by ID"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        model = result.scalar_one()
        for key, value in data.items():
            setattr(model, key, value)
        await self.session.flush()
        return model