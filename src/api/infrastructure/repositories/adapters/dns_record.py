"""DNS record repository"""

from uuid import UUID

from api.domain.models import DNSRecordModel
from api.infrastructure.repositories.adapters.base import \
    SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.dns_record import \
    DNSRecordRepository


class SQLAlchemyDNSRecordRepository(SQLAlchemyAbstractRepository, DNSRecordRepository):
    model = DNSRecordModel

    async def ensure(
        self,
        host_id: UUID,
        record_type: str,
        value: str,
        ttl: int | None = None,
        priority: int | None = None,
        is_wildcard: bool = False,
    ) -> DNSRecordModel:

        entity = DNSRecordModel(
            host_id=host_id,
            record_type=record_type,
            value=value,
            ttl=ttl,
            priority=priority,
            is_wildcard=is_wildcard
        )

        return await self.upsert(
            entity,
            conflict_fields=["host_id", "record_type", "value"],
            update_fields=["ttl", "priority", "is_wildcard"]
        )
