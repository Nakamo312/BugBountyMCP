from abc import ABC, abstractmethod
from typing import Self


class AbstractUnitOfWork(ABC):
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Full rollback of the transaction"""
        raise NotImplementedError

    @abstractmethod
    async def create_savepoint(self, name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback_to_savepoint(self, name: str) -> None:
        """Rollback only to a given savepoint"""
        raise NotImplementedError

    @abstractmethod
    async def release_savepoint(self, name: str) -> None:
        """Remove a savepoint after successful work"""
        raise NotImplementedError
