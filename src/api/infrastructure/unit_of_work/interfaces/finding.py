"""Finding Unit of Work interface"""

from abc import ABC

from api.infrastructure.repositories.interfaces.finding import FindingRepository
from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class FindingUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for finding operations"""
    
    findings: FindingRepository
    hosts: HostRepository
    endpoints: EndpointRepository
