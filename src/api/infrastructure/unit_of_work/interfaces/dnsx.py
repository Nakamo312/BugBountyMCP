from abc import ABC

from api.infrastructure.repositories.interfaces.dns_record import \
    DNSRecordRepository
from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.scope_rule import \
    ScopeRuleRepository
from api.infrastructure.unit_of_work.interfaces.base import \
    AbstractUnitOfWork


class DNSxUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for DNSx operations"""

    hosts: HostRepository
    dns_records: DNSRecordRepository
    scope_rules: ScopeRuleRepository
