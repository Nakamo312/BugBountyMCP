"""Naabu Unit of Work Interface"""

from abc import ABC
from api.infrastructure.repositories.interfaces.ip_address import IPAddressRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository
from api.infrastructure.repositories.interfaces.scope_rule import ScopeRuleRepository
from api.infrastructure.repositories.interfaces.host import HostRepository


class AbstractNaabuUnitOfWork(ABC):
    """
    Unit of Work interface for Naabu port scan ingestion.

    Provides access to:
    - ip_addresses: IP address repository
    - services: Service repository
    - scope_rules: Scope rule repository
    - hosts: Host repository (for smap hostnames)
    """

    ip_addresses: IPAddressRepository
    services: ServiceRepository
    scope_rules: ScopeRuleRepository
    hosts: HostRepository
