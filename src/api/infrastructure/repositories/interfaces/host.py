"""Host repository"""

from abc import ABC
from uuid import UUID
from api.domain.models import  HostModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository




class HostRepository(AbstractRepository[HostModel], ABC):
    async def ensure(
        self,
        program_id: UUID,
        host: str,
        in_scope: bool = True,
        cname: list[str] | None = None,
    ) -> HostModel:
        raise NotImplementedError