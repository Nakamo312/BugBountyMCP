"""Infrastructure Unit of Work adapter for graph visualization"""

from api.infrastructure.repositories.adapters.asn import SQLAlchemyASNRepository
from api.infrastructure.repositories.adapters.cidr import SQLAlchemyCIDRRepository
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.ip_address import SQLAlchemyIPAddressRepository
from api.infrastructure.repositories.adapters.host_ip import SQLAlchemyHostIPRepository
from api.infrastructure.repositories.adapters.service import SQLAlchemyServiceRepository
from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork


class SQLAlchemyInfrastructureUnitOfWork(SQLAlchemyAbstractUnitOfWork, InfrastructureUnitOfWork):
    """SQLAlchemy implementation of Infrastructure Unit of Work"""

    async def __aenter__(self):
        await super().__aenter__()
        self.asns = SQLAlchemyASNRepository(session=self._session)
        self.cidrs = SQLAlchemyCIDRRepository(session=self._session)
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        self.ips = SQLAlchemyIPAddressRepository(session=self._session)
        self.host_ips = SQLAlchemyHostIPRepository(session=self._session)
        self.services = SQLAlchemyServiceRepository(session=self._session)
        return self
