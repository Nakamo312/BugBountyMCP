"""ASNMap Unit of Work adapter"""

from api.infrastructure.repositories.adapters.asn import SQLAlchemyASNRepository
from api.infrastructure.repositories.adapters.cidr import SQLAlchemyCIDRRepository
from api.infrastructure.repositories.adapters.organization import SQLAlchemyOrganizationRepository
from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.asnmap import ASNMapUnitOfWork


class SQLAlchemyASNMapUnitOfWork(SQLAlchemyAbstractUnitOfWork, ASNMapUnitOfWork):
    """SQLAlchemy implementation of ASNMap Unit of Work"""

    async def __aenter__(self):
        await super().__aenter__()
        self.organizations = SQLAlchemyOrganizationRepository(session=self._session)
        self.asns = SQLAlchemyASNRepository(session=self._session)
        self.cidrs = SQLAlchemyCIDRRepository(session=self._session)

        return self
