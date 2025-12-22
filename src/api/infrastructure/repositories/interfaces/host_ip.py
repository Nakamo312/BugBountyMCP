"""Host-IP mapping repository"""
from uuid import UUID

from api.domain.models import HostIPModel
from api.infrastructure.repositories.interfaces.repository import AbstractRepository


class HostIPRepository(AbstractRepository[HostIPModel]):
    """Repository for HostIP mapping entities"""
    
    model = HostIPModel
    unique_fields = [("host_id", "ip_id")]
    async def link(self, host_id: UUID, ip_id: UUID, source: str) -> HostIPModel:
        raise NotImplementedError