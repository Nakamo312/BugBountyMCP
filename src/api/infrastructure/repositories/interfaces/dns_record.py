"""DNS record repository"""

from abc import ABC
from uuid import UUID

from api.domain.models import DNSRecordModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class DNSRecordRepository(AbstractRepository[DNSRecordModel], ABC):
    async def ensure(
        self,
        host_id: UUID,
        record_type: str,
        value: str,
        ttl: int | None = None,
        priority: int | None = None,
        is_wildcard: bool = False,
    ) -> DNSRecordModel:
        raise NotImplementedError
