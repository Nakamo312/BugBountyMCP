
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
from api.domain.models import EndpointModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class EndpointRepository(AbstractRepository[EndpointModel], ABC):
    @abstractmethod
    async def ensure(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        normalized_path: str,
        method: str,
        status_code: int | None,
    ) -> EndpointModel:
        raise NotImplementedError
    
    async def find_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[EndpointModel]:
        """Find endpoints by host_id"""
        raise NotImplementedError