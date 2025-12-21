from typing import Optional
from uuid import UUID

from sqlalchemy import select
from api.infrastructure.database.models import HostIPModel
from api.infrastructure.repositories.base_repo import BaseRepository



class HostIPRepository(BaseRepository[HostIPModel]):
    """PostgreSQL implementation of HostIP repository"""

    model = HostIPModel
    unique_fields = [('host_id', 'ip_id')]

    async def exists(self, host_id: UUID, ip_id: UUID) -> bool:
        """Check if host-ip link exists"""
        return await self.exists_by_unique_fields(host_id=host_id, ip_id=ip_id)

    async def link(
        self, host_id: UUID, ip_id: UUID, source: str
    ) -> Optional[HostIPModel]:
        """Create host-ip link if doesn't exist"""
        link, created = await self.get_or_create(
            host_id=host_id,
            ip_id=ip_id,
            defaults={'source': source}
        )
        return link if created else None