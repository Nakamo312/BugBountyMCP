"""IP Address repository"""
from abc import ABC
from uuid import UUID
from api.domain.models import IPAddressModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository



class IPAddressRepository(AbstractRepository[IPAddressModel], ABC):
    async def ensure(
        self,
        program_id: UUID,
        address: str,
        in_scope: bool = True,
    ) -> IPAddressModel:
        raise NotImplementedError
