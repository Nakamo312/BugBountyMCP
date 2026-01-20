from abc import ABC, abstractmethod
from typing import Self

from api.domain.repositories import (
    IProgramRepository,
    IHostRepository,
    IIPAddressRepository,
    IHostIPRepository,
    IServiceRepository,
    IEndpointRepository,
    IInputParameterRepository,
    IHeaderRepository,
)


class IUnitOfWork(ABC):
    programs: IProgramRepository
    hosts: IHostRepository
    ip_addresses: IIPAddressRepository
    host_ips: IHostIPRepository
    services: IServiceRepository
    endpoints: IEndpointRepository
    input_parameters: IInputParameterRepository
    headers: IHeaderRepository

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError
