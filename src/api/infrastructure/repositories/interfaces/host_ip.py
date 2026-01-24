from abc import ABC
from typing import List
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

    async def find_by_program_id(self, program_id: UUID) -> List[HostIPModel]:
        """Find all host-IP mappings for a program (joins with hosts)"""
        raise NotImplementedError
