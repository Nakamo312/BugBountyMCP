"""Header repository"""

from abc import ABC
from typing import List
from uuid import UUID

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository



class HeaderRepository(AbstractRepository[HeaderModel], ABC):
    """Repository for Header entities"""
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[HeaderModel]:
        """Find headers by endpoint_id"""
        raise NotImplementedError
