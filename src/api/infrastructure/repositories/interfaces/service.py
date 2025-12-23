from abc import ABC
from uuid import UUID
from typing import Dict
from api.domain.models import ServiceModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class ServiceRepository(AbstractRepository[ServiceModel], ABC):
    async def ensure(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Dict[str, bool],
    ) -> ServiceModel:
        raise NotImplementedError
