"""SQLAlchemy abstract repository with default implementations"""

from typing import Any, Dict, List, Optional, Tuple, Type
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class SQLAlchemyAbstractRepository(AbstractRepository):
    """
    Base SQLAlchemy repository with default implementations.
    Concrete repositories should set the `model` class attribute.
    """

    model: Type = None

    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def get(self, id: UUID) -> Optional[Any]:
        """
        Get entity by ID.

        Args:
            id: Entity UUID

        Returns:
            Entity or None if not found
        """
        if not self.model:
            raise NotImplementedError("Model not specified in repository")

        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_fields(self, **filters) -> Optional[Any]:
        """
        Get entity by field values.

        Args:
            **filters: Field name to value mapping

        Returns:
            Entity or None if not found
        """
        if not self.model:
            raise NotImplementedError("Model not specified in repository")

        conditions = []
        for key, value in filters.items():
            if hasattr(self.model, key):
                conditions.append(getattr(self.model, key) == value)

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
    ) -> List[Any]:
        """
        Find multiple entities with pagination and ordering.

        Args:
            filters: Optional filter dictionary
            limit: Maximum number of results
            offset: Results offset
            order_by: Field to order by (prefix with '-' for descending)

        Returns:
            List of entities
        """
        if not self.model:
            raise NotImplementedError("Model not specified in repository")

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
            elif hasattr(self.model, order_by):
                query = query.order_by(getattr(self.model, order_by))

        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities matching filters.

        Args:
            filters: Optional filter dictionary

        Returns:
            Number of matching entities
        """
        if not self.model:
            raise NotImplementedError("Model not specified in repository")

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

    async def create(self, entity: Any) -> Any:
        """
        Create new entity.

        Args:
            entity: Entity to create

        Returns:
            Created entity
        """
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, id: UUID, entity: Any) -> Any:
        """
        Update existing entity.

        Args:
            id: Entity UUID
            entity: Updated entity data

        Returns:
            Updated entity

        Raises:
            EntityNotFound: If entity does not exist
        """
        existing = await self.get(id)
        if not existing:
            raise EntityNotFound(f"Entity with id {id} not found")

        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)

        await self.session.flush()
        return existing

    async def delete(self, id: UUID) -> None:
        """
        Delete entity by ID.

        Args:
            id: Entity UUID
        """
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()

    async def get_or_create(
        self,
        entity: Any,
    ) -> Tuple[Any, bool]:
        """
        Get existing entity or create new one.

        Args:
            entity: Entity to create if not exists

        Returns:
            Tuple of (entity, created) where created is True if new
        """
        filters = {
            key: value for key, value in entity.__dict__.items()
            if not key.startswith('_')
        }

        existing = await self.get_by_fields(**filters)
        if existing:
            return existing, False

        created = await self.create(entity)
        return created, True

    async def upsert(
        self,
        entity: Any,
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> Any:
        """
        Insert or update entity.

        Args:
            entity: Entity to upsert
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict

        Returns:
            Upserted entity
        """
        try:
            created = await self.create(entity)
            return created
        except Exception:
            return await self.update(entity.id, entity)

    async def bulk_create(self, entities: List[Any]) -> List[Any]:
        """
        Create multiple entities.

        Args:
            entities: List of entities to create

        Returns:
            List of created entities
        """
        if not entities:
            return []

        self.session.add_all(entities)
        await self.session.flush()
        return entities

    async def bulk_upsert(
        self,
        entities: List[Any],
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> None:
        """
        Insert or update multiple entities.

        Args:
            entities: List of entities to upsert
            conflict_fields: Fields to check for conflicts
            update_fields: Fields to update on conflict
        """
        for entity in entities:
            try:
                await self.upsert(entity, conflict_fields, update_fields)
            except Exception:
                continue