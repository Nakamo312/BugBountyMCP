# api/infrastructure/unit_of_work/adapters/base.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class SQLAlchemyAbstractUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None
        self._savepoints: list[str] = []

    async def __aenter__(self):
        self._session = self.session_factory()
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await super().__aexit__(exc_type, exc_val, exc_tb)
        if self._session:
            await self._session.close()

    async def commit(self):
        if self._session:
            await self._session.commit()

    async def rollback(self):
        """Full rollback"""
        if self._session:
            await self._session.rollback()
            self._savepoints.clear()

    async def create_savepoint(self, name: str):
        if not self._session:
            raise RuntimeError("Session not initialized")
        await self._session.execute(text(f"SAVEPOINT {name}"))
        self._savepoints.append(name)
    
    async def rollback_to_savepoint(self, name: str):
        if not self._session:
            return
        if name not in self._savepoints:
            raise ValueError(f"Savepoint {name} does not exist")
        await self._session.execute(text(f"ROLLBACK TO SAVEPOINT {name}"))
        idx = self._savepoints.index(name)
        self._savepoints = self._savepoints[:idx]
    
    async def release_savepoint(self, name: str):
        if not self._session:
            return
        if name not in self._savepoints:
            raise ValueError(f"Savepoint {name} does not exist")
        await self._session.execute(text(f"RELEASE SAVEPOINT {name}"))
        self._savepoints.remove(name)
    