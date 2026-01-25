from abc import ABC

from api.infrastructure.repositories.interfaces.dns_record import \
    DNSRecordRepository
from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.ip_address import \
    IPAddressRepository
from api.infrastructure.repositories.interfaces.host_ip import \
    HostIPRepository
from api.infrastructure.repositories.interfaces.scope_rule import \
    ScopeRuleRepository
from api.infrastructure.unit_of_work.interfaces.base import \
    AbstractUnitOfWork


class DNSxUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for DNSx operations"""

    hosts: HostRepository
    ip_addresses: IPAddressRepository
    host_ips: HostIPRepository
    dns_records: DNSRecordRepository
    scope_rules: ScopeRuleRepository
