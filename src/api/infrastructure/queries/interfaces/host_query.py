from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from api.domain.models import HostModel
from api.infrastructure.queries.interfaces.base import AbstractQueryRepository



class HostQuery(AbstractQueryRepository[HostModel], ABC):
    model = HostModel

    @abstractmethod
    async def get(self, id: UUID) -> Optional[HostModel]:
        raise NotImplementedError

    @abstractmethod
    async def find_by_fields(self, **filters) -> Optional[HostModel]:
        raise NotImplementedError

    @abstractmethod
    async def list(self, filters: Optional[Dict[str, Any]] = None) -> List[HostModel]:
        raise NotImplementedError

    @abstractmethod
    async def get_host(self, program_id: UUID, host: str) -> Optional[HostModel]:
        raise NotImplementedError

    @abstractmethod
    async def list_hosts(self, program_id: UUID) -> List[HostModel]:
        raise NotImplementedError