
from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import UUID
from api.domain.models import EndpointModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class EndpointRepository(AbstractRepository[EndpointModel], ABC):
    @abstractmethod
    async def upsert_with_method(
        self,
        host_id: UUID,
        service_id: UUID,
        path: str,
        method: str,
        normalized_path: str,
        status_code: Optional[int] = None,
        **kwargs
    ) -> EndpointModel:
        raise NotImplementedError
    
    @abstractmethod
    async def find_by_host(self, host_id: UUID) -> List[EndpointModel]:
        raise NotImplementedError
    
    @abstractmethod
    async def find_by_service(self, service_id: UUID) -> List[EndpointModel]:
        raise NotImplementedError