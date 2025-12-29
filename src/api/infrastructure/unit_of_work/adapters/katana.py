from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.ip_address import SQLAlchemyIPAddressRepository
from api.infrastructure.repositories.adapters.host_ip import SQLAlchemyHostIPRepository
from api.infrastructure.repositories.adapters.service import SQLAlchemyServiceRepository
from api.infrastructure.repositories.adapters.endpoint import SQLAlchemyEndpointRepository
from api.infrastructure.repositories.adapters.input_parameters import SQLAlchemyInputParameterRepository
from api.infrastructure.repositories.adapters.header import SQLAlchemyHeaderRepository
from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.katana import KatanaUnitOfWork


class SQLAlchemyKatanaUnitOfWork(SQLAlchemyAbstractUnitOfWork, KatanaUnitOfWork):
    """SQLAlchemy implementation of Katana Unit of Work"""

    async def __aenter__(self):
        await super().__aenter__()
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        self.ips = SQLAlchemyIPAddressRepository(session=self._session)
        self.host_ips = SQLAlchemyHostIPRepository(session=self._session)
        self.services = SQLAlchemyServiceRepository(session=self._session)
        self.endpoints = SQLAlchemyEndpointRepository(session=self._session)
        self.input_parameters = SQLAlchemyInputParameterRepository(session=self._session)
        self.headers = SQLAlchemyHeaderRepository(session=self._session)

        return self
