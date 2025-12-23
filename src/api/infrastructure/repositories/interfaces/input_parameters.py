"""Input parameter repository"""
from abc import ABC
from typing import Dict
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
