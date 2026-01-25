"""Naabu Unit of Work Adapter"""

from api.infrastructure.unit_of_work.adapters.base import SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.infrastructure.repositories.adapters.ip_address import SQLAlchemyIPAddressRepository
from api.infrastructure.repositories.adapters.service import SQLAlchemyServiceRepository
from api.infrastructure.repositories.adapters.scope_rule import SQLAlchemyScopeRuleRepository
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository


class SQLAlchemyNaabuUnitOfWork(SQLAlchemyAbstractUnitOfWork, AbstractNaabuUnitOfWork):
    """
    SQLAlchemy implementation of Naabu Unit of Work.

    Manages:
    - IP addresses (ensure IP exists)
    - Services (create/update port records)
    - Scope rules (for hostname filtering)
    - Hosts (for smap discovered hostnames)
    """

    async def __aenter__(self):
        await super().__aenter__()
        self.ip_addresses = SQLAlchemyIPAddressRepository(session=self._session)
        self.services = SQLAlchemyServiceRepository(session=self._session)
        self.scope_rules = SQLAlchemyScopeRuleRepository(session=self._session)
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        return self
