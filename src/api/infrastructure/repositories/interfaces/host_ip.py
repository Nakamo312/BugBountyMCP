from abc import ABC
from uuid import UUID
from api.domain.models import HostIPModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class HostIPRepository(AbstractRepository[HostIPModel], ABC):
    async def ensure(
        self,
        host_id: UUID,
        ip_id: UUID,
        source: str,
    ) -> HostIPModel:
        raise NotImplementedError
