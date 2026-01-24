"""Infrastructure Unit of Work interface for graph visualization"""

from abc import ABC

from api.infrastructure.repositories.interfaces.asn import ASNRepository
from api.infrastructure.repositories.interfaces.cidr import CIDRRepository
from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.ip_address import IPAddressRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class InfrastructureUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for infrastructure graph operations"""

    asns: ASNRepository
    cidrs: CIDRRepository
    hosts: HostRepository
    ips: IPAddressRepository
    host_ips: HostIPRepository
    services: ServiceRepository
