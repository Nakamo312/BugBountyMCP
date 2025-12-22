from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork

class SQLAlchemyAbstractUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self._session: AsyncSession = None
    
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
        if self._session:
            await self._session.rollback()