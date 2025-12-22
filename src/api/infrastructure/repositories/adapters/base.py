# api/infrastructure/repositories/adapters/base.py
"""SQLAlchemy abstract repository with default implementations"""

from typing import Any, Dict, List, Optional, Tuple, Type
from uuid import UUID

from sqlalchemy import select, func, and_, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from api.infrastructure.exception.exceptions import EntityNotFound
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class SQLAlchemyAbstractRepository(AbstractRepository):
    model: Type = None

    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def get(self, id: UUID) -> Optional[Any]:
        if not self.model:
            raise NotImplementedError("Model not specified in repository")

        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_fields(self, **filters) -> Optional[Any]:
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
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, id: UUID, entity: Any) -> Any:
        existing = await self.get(id)
        if not existing:
            raise EntityNotFound(f"Entity with id {id} not found")

        for key, value in entity.__dict__.items():
            if not key.startswith('_') and key != 'id' and hasattr(existing, key):
                setattr(existing, key, value)

        await self.session.flush()
        return existing

    async def delete(self, id: UUID) -> None:
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()

    async def get_or_create(
        self,
        entity: Any,
    ) -> Tuple[Any, bool]:
        filters = {
            key: value for key, value in entity.__dict__.items()
            if not key.startswith('_')
        }

        existing = await self.get_by_fields(**filters)
        if existing:
            return existing, False

        created = await self.create(entity)
        return created, True

    def _get_constraint_name(self, table, conflict_fields: List[str]) -> str:
        mapper = inspect(self.model)
        table_obj = mapper.persist_selectable
        
        for constraint in table_obj.constraints:
            if hasattr(constraint, 'columns'):
                constraint_cols = {col.name for col in constraint.columns}
                if constraint_cols == set(conflict_fields):
                    return constraint.name
        
        return f"uq_{table.name}_{'_'.join(conflict_fields)}"

    async def upsert(
        self,
        entity: Any,
        conflict_fields: List[str],
        update_fields: Optional[List[str]] = None
    ) -> Any:
        if not self.model:
            raise NotImplementedError("Model not specified in repository")
        
        entity_dict = {
            k: v for k, v in entity.__dict__.items() 
            if not k.startswith('_')
        }
        
        table = self.model.__table__
        stmt = insert(table).values(entity_dict)
        
        constraint_name = self._get_constraint_name(table, conflict_fields)
        
        if update_fields:
            update_dict = {
                col: stmt.excluded[col]
                for col in update_fields
            }
            stmt = stmt.on_conflict_do_update(
                constraint=constraint_name,
                set_=update_dict
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                constraint=constraint_name
            )
        
        await self.session.execute(stmt)
        await self.session.flush()
        
        existing = await self.get_by_fields(**{
            field: entity_dict[field] for field in conflict_fields
        })
        return existing

    async def bulk_create(self, entities: List[Any]) -> List[Any]:
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
        if not entities:
            return
        
        if not self.model:
            raise NotImplementedError("Model not specified in repository")
        
        values = [
            {k: v for k, v in entity.__dict__.items() if not k.startswith('_')}
            for entity in entities
        ]
        
        table = self.model.__table__
        stmt = insert(table).values(values)
        
        constraint_name = self._get_constraint_name(table, conflict_fields)
        
        if update_fields:
            update_dict = {
                col: stmt.excluded[col]
                for col in update_fields
            }
            stmt = stmt.on_conflict_do_update(
                constraint=constraint_name,
                set_=update_dict
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                constraint=constraint_name
            )
        
        await self.session.execute(stmt)
        await self.session.flush()