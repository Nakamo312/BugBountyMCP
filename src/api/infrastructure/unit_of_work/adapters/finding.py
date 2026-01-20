"""Finding Unit of Work implementation"""

from api.infrastructure.repositories.adapters.finding import SQLAlchemyFindingRepository
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.endpoint import SQLAlchemyEndpointRepository
from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.finding import FindingUnitOfWork


class SQLAlchemyFindingUnitOfWork(SQLAlchemyAbstractUnitOfWork, FindingUnitOfWork):
    """SQLAlchemy implementation of Finding Unit of Work"""
    
    async def __aenter__(self):
        await super().__aenter__()
        self.findings = SQLAlchemyFindingRepository(session=self._session)
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        self.endpoints = SQLAlchemyEndpointRepository(session=self._session)
        
        return self
