from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from uuid import UUID

from src.api.domain.models import AbstractModel

class AbstractQueryRepository(ABC):
    """Базовый контракт для чтения сущностей"""

    model: type[AbstractModel]

    @abstractmethod
    async def get(self, id: UUID) -> Optional[AbstractModel]:
        raise NotImplementedError

    @abstractmethod
    async def find_by_fields(self, **filters) -> Optional[AbstractModel]:
        raise NotImplementedError

    @abstractmethod
    async def list(self, filters: Optional[Dict[str, Any]] = None) -> List[AbstractModel]:
        raise NotImplementedError
