"""Host repository"""

from abc import ABC
from typing import List
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
    
    async def find_by_program(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        in_scope: bool | None = None
    ) -> List[HostModel]:
        """Find hosts by program_id with optional filters"""
        raise NotImplementedError