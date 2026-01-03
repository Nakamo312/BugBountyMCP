from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from api.domain.models import LeakModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class LeakRepository(AbstractRepository[LeakModel], ABC):
    @abstractmethod
    async def find_by_program(self, program_id: UUID) -> List[LeakModel]:
        raise NotImplementedError

    @abstractmethod
    async def ensure(
        self,
        program_id: UUID,
        content: str,
        endpoint_id: UUID | None = None,
    ) -> LeakModel:
        raise NotImplementedError
