"""Input parameter repository"""
from abc import ABC
from typing import Dict, List
from uuid import UUID
from api.domain.models import InputParameterModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository



class InputParameterRepository(AbstractRepository[InputParameterModel], ABC):
    async def ensure(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Dict[str, bool],
    ) -> InputParameterModel:
        raise NotImplementedError
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[InputParameterModel]:
        """Find input parameters by endpoint_id"""
        raise NotImplementedError