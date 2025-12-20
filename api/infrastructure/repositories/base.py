from abc import ABC
from typing import Generic, TypeVar, Optional, List
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

Model = TypeVar("Model")


class BaseRepository(ABC, Generic[Model]):
    model: type[Model]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[Model]:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def delete(self, id: UUID) -> None:
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()

    async def list_all(self) -> List[Model]:
        result = await self.session.execute(select(self.model))
        return result.scalars().all()
