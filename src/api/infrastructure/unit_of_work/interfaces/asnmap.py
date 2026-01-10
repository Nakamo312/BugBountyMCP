"""ASNMap Unit of Work interface"""

from abc import ABC

from api.infrastructure.repositories.interfaces.asn import ASNRepository
from api.infrastructure.repositories.interfaces.cidr import CIDRRepository
from api.infrastructure.repositories.interfaces.organization import OrganizationRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class ASNMapUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for ASNMap operations"""

    organizations: OrganizationRepository
    asns: ASNRepository
    cidrs: CIDRRepository
