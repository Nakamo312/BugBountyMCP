from api.infrastructure.repositories.adapters.dns_record import \
    SQLAlchemyDNSRecordRepository
from api.infrastructure.repositories.adapters.host import \
    SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.scope_rule import \
    SQLAlchemyScopeRuleRepository
from api.infrastructure.unit_of_work.adapters.base import \
    SQLAlchemyAbstractUnitOfWork
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork


class SQLAlchemyDNSxUnitOfWork(SQLAlchemyAbstractUnitOfWork, DNSxUnitOfWork):
    """SQLAlchemy implementation of DNSx Unit of Work"""

    async def __aenter__(self):
        await super().__aenter__()
        self.hosts = SQLAlchemyHostRepository(session=self._session)
        self.dns_records = SQLAlchemyDNSRecordRepository(session=self._session)
        self.scope_rules = SQLAlchemyScopeRuleRepository(session=self._session)

        return self
