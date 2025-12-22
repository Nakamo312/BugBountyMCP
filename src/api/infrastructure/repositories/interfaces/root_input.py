
from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from api.domain.models import RootInputModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class RootInputRepository(AbstractRepository[RootInputModel], ABC):
    @abstractmethod
    async def find_by_program(self, program_id: UUID) -> List[RootInputModel]:
        raise NotImplementedError