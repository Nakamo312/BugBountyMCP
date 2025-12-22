"""Service repository"""
from typing import Dict
from uuid import UUID

from api.domain.models import ServiceModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class ServiceRepository(AbstractRepository[ServiceModel]):
    model = ServiceModel
    unique_fields = [("ip_id", "scheme", "port")]
    
    async def get_or_create_with_tech(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Dict[str, bool]
    ) -> ServiceModel : raise NotImplementedError
        