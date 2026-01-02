from abc import ABC

from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.ip_address import IPAddressRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository
from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.repositories.interfaces.input_parameters import InputParameterRepository
from api.infrastructure.repositories.interfaces.header import HeaderRepository
from api.infrastructure.repositories.interfaces.scope_rule import ScopeRuleRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class KatanaUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for Katana scan operations"""

    hosts: HostRepository
    ips: IPAddressRepository
    host_ips: HostIPRepository
    services: ServiceRepository
    endpoints: EndpointRepository
    input_parameters: InputParameterRepository
    headers: HeaderRepository
    scope_rules: ScopeRuleRepository
