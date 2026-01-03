from api.infrastructure.repositories.adapters.leak import SQLAlchemyLeakRepository
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.endpoint import SQLAlchemyEndpointRepository
from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.mantra import MantraUnitOfWork


class SQLAlchemyMantraUnitOfWork(SQLAlchemyAbstractUnitOfWork, MantraUnitOfWork):
    """SQLAlchemy implementation of Mantra Unit of Work"""

    async def __aenter__(self):
        await super().__aenter__()
        self.leaks = SQLAlchemyLeakRepository(session=self._session)
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        self.endpoints = SQLAlchemyEndpointRepository(session=self._session)

        return self
