from abc import ABC

from api.infrastructure.repositories.interfaces.leak import LeakRepository
from api.infrastructure.repositories.interfaces.host import HostRepository
from api.infrastructure.repositories.interfaces.endpoint import EndpointRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class MantraUnitOfWork(AbstractUnitOfWork, ABC):
    """Unit of Work interface for Mantra scan operations"""

    leaks: LeakRepository
    hosts: HostRepository
    endpoints: EndpointRepository
